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


def get_data(raw_data: bytes | str) -> tuple[str, float, float]:
    """Get the data from a raw WS message.

    Parameters
    ----------
    raw_data: bytes | str
        The raw WS message.

    Returns
    -------
    tuple[str, float, float]
        The user ID, the x coordinate and the y coordinate.

    Raises
    ------
    ValueError
        If the data is invalid. The error will have two args:
        - The error message (with %s placeholder for the specific data that caused the error (see below))
        - The specific data that caused the error to be raised.
    """
    # pylint warns us that we have a unused `%s` in the error message, but it's to let the called handled the message +
    # value like it wants (using `%` or not, for example with logging)
    # pylint: disable=raising-format-tuple

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON: %s", raw_data) from exc

    if (
        not all(isinstance(key, str) for key in data)
        or not all(isinstance(value, str) for value in data.values())
        or len(data) != 4
    ):
        raise ValueError("Invalid data: %s", data)

    try:
        message_type = data["type"]
        user_id = data["id"]
        x_relative_str = data["x"]
        y_relative_str = data["y"]
    except KeyError as exc:
        raise ValueError("Invalid data: %s", data) from exc

    if message_type != "click":
        raise ValueError("Invalid data type: %s", message_type)
    if not user_id:
        raise ValueError("Invalid user ID: %s", user_id)
    if not valid_number_re.match(x_relative_str):
        raise ValueError("Invalid x: %s", x_relative_str)
    if not valid_number_re.match(y_relative_str):
        raise ValueError("Invalid y: %s", y_relative_str)
    if not 0 <= (x_relative := float(x_relative_str)) <= 1:
        raise ValueError("Invalid x: %s", x_relative)
    if not 0 <= (y_relative := float(y_relative_str)) <= 1:
        raise ValueError("Invalid y: %s", y_relative)

    return user_id, x_relative, y_relative


async def get_user_name(user_id: str, http: aiohttp.ClientSession, get_url: str = GET_USER_URL) -> str:
    """Get the username of a user from their ID.

    Parameters
    ----------
    user_id: str
        The ID of the user.
    http: aiohttp.ClientSession
        The HTTP session to use.
    get_url: str
        The URL to use to get the user's name.

    Returns
    -------
    str
        The user's name.

    Raises
    ------
    ValueError
        - If the user id starts with "A" (anonymous) or "U" (user that didn't accept to share it's ID).
        - If the Twitch API refused to return a user for this ud
        - If the user returned by the Twitch API has no `display_name` field..
    """
    if user_id.startswith("A"):
        raise ValueError("User %s is not logged in on Twitch.")
    if user_id.startswith("U"):
        raise ValueError("User %s did no accept to share it's ID")

    try:
        get_url = get_url.format(quote_plus(user_id))
        async with http.get(get_url) as response:
            user = await response.json()
    except aiohttp.ClientError as exc:
        raise ValueError("Failed to get user %s from Twitch API") from exc

    try:
        username = user["display_name"]
    except KeyError as exc:
        raise ValueError("User %s has no display_name") from exc

    if not isinstance(username, str):
        raise ValueError("User %s has an invalid display_name")

    return username


async def catch_clicks() -> None:
    """Catch clicks on the screen and print the targets."""
    async with aiohttp.ClientSession() as http:
        while True:
            async with connect(WS_URL) as websocket:
                while True:
                    try:
                        raw_data = await websocket.recv()
                    except ConnectionClosed:
                        logger.exception("WebSocket connection closed")
                        break
                    try:
                        try:
                            user_id, x_relative, y_relative = get_data(raw_data)
                        except ValueError as exc:
                            logger.error(str(exc.args[0]), *exc.args[1:])
                            continue
                        try:
                            username = await get_user_name(user_id, http, GET_USER_URL)
                        except ValueError as exc:
                            logger.error(str(exc), user_id)
                            refused_ids.add(user_id)
                            continue

                        x_absolute = int(x_relative * SCREEN_SIZE[0])
                        y_absolute = int(y_relative * SCREEN_SIZE[1])
                        target = get_click_target(x_absolute, y_absolute)
                        logger.info("%s clicked at on %s (%s, %s)", username, target, x_absolute, y_absolute)

                    except Exception:  # pylint: disable=broad-except
                        logger.exception("Unhandled exception while trying to process WS message: %s", raw_data)


if __name__ == "__main__":
    asyncio.run(catch_clicks())
