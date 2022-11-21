"""Get positions of clicks from users on Twitch via the Heat extension.

Inspired by https://github.com/scottgarner/Heat/blob/master/js/heat.js

Extension: https://dashboard.twitch.tv/extensions/cr20njfkgll4okyrhag7xxph270sqk-2.1.1

https://dashboard.twitch.tv/extensions/nyu70xf8pcgznu09ho55zo9x5z6ao8-0.0.1

"""

import asyncio
import json
import logging
import re

from websockets.exceptions import ConnectionClosed
from websockets.legacy.client import connect

from .utils import (
    ClickCallback,
    get_twitch_client,
    handle_click,
    init_refused_ids,
    standalone_runner,
)

CHANNEL_ID = 820553075
WS_URL = f"wss://heat-api.j38.net/channel/{CHANNEL_ID}"
GET_USER_URL = "https://heat-api.j38.net/user/{}"
valid_number_re = re.compile(r"^((1(\.0)?)|(0(\.\d+)?))$")

logger = logging.getLogger("hexpo_game.click_provider.heat")


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
        If the data is invalid. The error will have 3 args (in ``exc_object.args``):
        - The error message (with ``%s`` placeholder for the specific data that caused the error (see below))
        - The specific data that caused the error to be raised.
        - The user id found inn the message if any (for example to store it to ignore its next messages)
    """
    # pylint warns us that we have an unused `%s` in the error message, but it's to let the called handled the message +
    # value like it wants (using `%` or not, for example with logging)
    # pylint: disable=raising-format-tuple

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON: %s", raw_data) from exc

    data.pop("modifier", None)
    data.pop("modifiers", None)
    if (
        not all(isinstance(key, str) for key in data)
        or not all(isinstance(value, str) for value in data.values())
        or len(data) != 4
    ):
        raise ValueError("Invalid data: %s", data)

    user_id = None
    try:
        user_id = data["id"]
        message_type = data["type"]
        x_relative_str = data["x"]
        y_relative_str = data["y"]
    except KeyError as exc:
        raise ValueError("Invalid data: %s", data, user_id) from exc

    if message_type != "click":
        raise ValueError("Invalid data type: %s", message_type, user_id)
    if not user_id:
        raise ValueError("Invalid user ID: %s", user_id, user_id)
    if not valid_number_re.match(x_relative_str):
        raise ValueError("Invalid x: %s", x_relative_str, user_id)
    if not valid_number_re.match(y_relative_str):
        raise ValueError("Invalid y: %s", y_relative_str, user_id)
    if not 0 <= (x_relative := float(x_relative_str)) <= 1:
        raise ValueError("Invalid x: %s", x_relative, user_id)
    if not 0 <= (y_relative := float(y_relative_str)) <= 1:
        raise ValueError("Invalid y: %s", y_relative, user_id)

    return user_id, x_relative, y_relative


async def catch_clicks(twitch_app_token: str, callback: ClickCallback) -> None:
    """Catch clicks on the screen and print the targets.

    Parameters
    ----------
    twitch_app_token: str
        The Twitch app token to use.
    callback: ClickCallback
        The callback to call when a click is received.

    Raises
    ------
    RuntimeError
        - if TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET are not set in the environment.
        - if the Twitch app token could not be retrieved.

    """
    twitch_client = await get_twitch_client(twitch_app_token)
    refused_ids: set[str] = await init_refused_ids()

    while True:
        async with connect(WS_URL) as websocket:
            while True:
                try:
                    raw_data = await websocket.recv()
                except ConnectionClosed:
                    logger.exception("WebSocket connection closed")
                    break
                # logger.debug("Received: %s", raw_data)
                try:
                    try:
                        user_id, x_relative, y_relative = get_data(raw_data)
                    except ValueError as exc:
                        logger.error(str(exc.args[0]), *exc.args[1:])
                        if len(exc.args) > 2:
                            refused_ids.add(exc.args[2])
                        continue

                    await handle_click(user_id, x_relative, y_relative, twitch_client, refused_ids, callback)

                except Exception:  # pylint: disable=broad-except
                    logger.exception("Unhandled exception while trying to process WS message: %s", raw_data)


if __name__ == "__main__":
    asyncio.run(standalone_runner(catch_clicks))
