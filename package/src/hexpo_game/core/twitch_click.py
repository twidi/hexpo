"""Get targets clicked by users on Twitch.

Inspired by https://github.com/scottgarner/Heat/blob/master/js/heat.js
"""

import asyncio
import json
import logging
import re
from typing import Optional
from urllib.parse import quote_plus

import aiohttp
from websockets.exceptions import ConnectionClosed
from websockets.legacy.client import connect

CHANNEL_ID = 229962991
WS_URL = f"wss://heat-api.j38.net/channel/{CHANNEL_ID}"
GET_USER_URL = "https://heat-api.j38.net/user/{}"
valid_number_re = re.compile(r"^((1(\.0)?)|(0(\.\d+)?))$")

refused_ids: set[str] = set()

logger = logging.getLogger(__name__)


SCREEN_SIZE = (2560, 1440)
COORDINATES: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {  # ((left, top), (right, bottom))
    "action-btn-attack": ((10, 200), (92, 241)),
    "action-btn-defend": ((102, 200), (184, 241)),
    "action-btn-grow": ((194, 200), (276, 241)),
    "action-btn-bank": ((286, 200), (368, 241)),
}


def get_click_target(x_coord: int, y_coord: int) -> Optional[str]:
    """Return the target of the click, or None if the click is not on a target.

    Parameters
    ----------
    x_coord: int
        The x coordinate of the click.
    y_coord: int
        The y coordinate of the click.

    Returns
    -------
    Optional[str]
        The target of the click, or None if the click is not on a target.

    """
    for target_id, ((left, top), (right, bottom)) in COORDINATES.items():
        if left <= x_coord <= right and top <= y_coord <= bottom:
            return target_id
    return None


async def catch_clicks() -> None:
    """Catch clicks on the screen and print the targets."""
    # pylint: disable=too-many-branches,too-many-statements,too-many-locals
    # we assume that this code is long but there is no real way to split it easily
    async with aiohttp.ClientSession() as http:
        while True:
            async with connect(WS_URL) as websocket:
                while True:
                    try:
                        raw_message = await websocket.recv()
                    except ConnectionClosed:
                        logger.exception("WebSocket connection closed")
                        break
                    try:

                        try:
                            message = json.loads(raw_message)
                        except json.JSONDecodeError:
                            logger.error("Invalid JSON: %s", raw_message)
                            continue

                        try:
                            message_type = message["type"]
                            user_id = message["id"]
                            x_relative_str = message["x"]
                            y_relative_str = message["y"]
                        except KeyError:
                            logger.error("Invalid message: %s", message)
                            continue
                        if message_type != "click":
                            logger.error("Invalid message type: %s", message_type)
                            continue
                        if not user_id:
                            logger.error("Invalid user ID: %s", user_id)
                            continue
                        if not valid_number_re.match(x_relative_str):
                            logger.error("Invalid x: %s", x_relative_str)
                            continue
                        if not valid_number_re.match(y_relative_str):
                            logger.error("Invalid y: %s", y_relative_str)
                            continue

                        if not 0 <= (x_relative := float(x_relative_str)) <= 1:
                            logger.error("Invalid x: %s", x_relative)
                            continue
                        if not 0 <= (y_relative := float(y_relative_str)) <= 1:
                            logger.error("Invalid y: %s", y_relative)
                            continue

                        if user_id.startswith("A"):
                            if user_id not in refused_ids:
                                logger.error("User is anonymous: %s", user_id)
                                refused_ids.add(user_id)
                            continue
                        if user_id.startswith("U"):
                            if user_id not in refused_ids:
                                logger.error("User did not share its id: %s", user_id)
                                refused_ids.add(user_id)
                            continue

                        try:
                            get_url = GET_USER_URL.format(quote_plus(user_id))
                            async with http.get(get_url) as response:
                                user = await response.json()
                        except aiohttp.ClientError:
                            logger.error("Failed to get user: %s", user_id)
                            continue

                        try:
                            display_name = user["display_name"]
                        except KeyError:
                            logger.error("Invalid user: %s", user)
                            continue

                        x_absolute = int(x_relative * SCREEN_SIZE[0])
                        y_absolute = int(y_relative * SCREEN_SIZE[1])
                        target = get_click_target(x_absolute, y_absolute)
                        logger.info("%s clicked at on %s (%s, %s)", display_name, target, x_absolute, y_absolute)

                    except Exception:  # pylint: disable=broad-except
                        logger.exception("Unhandled exception while trying to process WS message: %s", raw_message)


if __name__ == "__main__":
    asyncio.run(catch_clicks())
