"""Get targets clicked by users on Twitch.

Inspired by https://github.com/scottgarner/Heat/blob/master/js/heat.js
"""

import asyncio
import json
import logging
import os
import re
from typing import Optional, cast

import aiohttp
from asgiref.sync import sync_to_async
from dotenv import load_dotenv
from twitchio import Client  # type: ignore[import]
from websockets.exceptions import ConnectionClosed
from websockets.legacy.client import connect

from hexpo_game.core.models import Player

CHANNEL_ID = 229962991
WS_URL = f"wss://heat-api.j38.net/channel/{CHANNEL_ID}"
GET_USER_URL = "https://heat-api.j38.net/user/{}"
valid_number_re = re.compile(r"^((1(\.0)?)|(0(\.\d+)?))$")

logger = logging.getLogger(__name__)


SCREEN_SIZE = (2560, 1440)
COORDINATES: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {  # ((left, top), (right, bottom))
    "action-btn-attack": ((10, 200), (92, 241)),
    "action-btn-defend": ((102, 200), (184, 241)),
    "action-btn-grow": ((194, 200), (276, 241)),
    "action-btn-bank": ((286, 200), (368, 241)),
}


async def get_twitch_app_token() -> str:
    """Get the Twitch app token.

    Returns
    -------
    str
        The Twitch app token.

    """
    load_dotenv()

    if not os.environ.get("TWITCH_CLIENT_ID"):
        raise RuntimeError("TWITCH_CLIENT_ID is not set. Please set it in .env or as an environment variable.")

    if not os.environ.get("TWITCH_CLIENT_SECRET"):
        raise RuntimeError("TWITCH_CLIENT_SECRET is not set. Please set it in .env or as an environment variable.")

    async with aiohttp.ClientSession() as session, session.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": os.environ["TWITCH_CLIENT_ID"],
            "client_secret": os.environ["TWITCH_CLIENT_SECRET"],
            "grant_type": "client_credentials",
        },
    ) as resp:
        return cast(str, (await resp.json())["access_token"])


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
        If the data is invalid. The error will have 3 args (in ``exc_object.args``):
        - The error message (with ``%s`` placeholder for the specific data that caused the error (see below))
        - The specific data that caused the error to be raised.
        - The user id found inn the message if any (for example to store it to ignore its next messages)
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


async def validate_user_id(user_id: str) -> int:
    """Check if the user ID is valid.

    Parameters
    ----------
    user_id: str
        The user ID to check.

    Returns
    -------
    int
        The validated user ID.

    Raises
    ------
    ValueError
        - If the user id starts with "A" (anonymous) or "U" (user that didn't accept to share its ID).
        - If the user id is not a number.

    """
    if user_id.startswith("A"):
        raise ValueError("User %s is not logged in on Twitch.")
    if user_id.startswith("U"):
        raise ValueError("User %s did no accept to share it's ID")
    try:
        return int(user_id)
    except ValueError:
        raise ValueError("User ID %s is not an integer") from None


async def fetch_user_name(user_id: int, twitch_client: Client) -> str:
    """Get the username of a user from their ID.

    Parameters
    ----------
    user_id: int
        The ID of the user.
    twitch_client: Client
        The Twitch client to use.

    Returns
    -------
    str
        The user's name.

    Raises
    ------
    ValueError
        - If the Twitch API refused to return a user for this id
    """
    try:
        return cast(str, (await twitch_client.fetch_users(ids=[user_id]))[0].display_name)
    except Exception as exc:  # pylint: disable=broad-except
        raise ValueError("Failed to get user %s from Twitch API") from exc


async def get_user_name(user_id: int, twitch_client: Client) -> str:
    """Get the username of a user from their ID.

    Parameters
    ----------
    user_id: int
        The ID of the user.
    twitch_client: Client
        The Twitch client to use.

    Returns
    -------
    str
        The user's name.

    """
    user: Optional[Player]
    try:
        user = await Player.objects.aget(external_id=user_id)
    except Player.DoesNotExist:
        user = username = None
    else:
        username = user.name

    if user is None or not username:
        username = await fetch_user_name(user_id, twitch_client)
        if user is None:
            await Player.objects.acreate(external_id=user_id, name=username)
        else:
            user.name = username
            await user.asave(update_fields=["name"])  # type: ignore[attr-defined]
    else:
        username = user.name

    return username


async def catch_clicks(twitch_app_token: str) -> None:
    """Catch clicks on the screen and print the targets.

    Parameters
    ----------
    twitch_app_token: str
        The Twitch app token to use.

    Raises
    ------
    RuntimeError
        - if TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET are not set in the environment.
        - if the Twitch app token could not be retrieved.

    """
    try:
        twitch_client = Client(token=twitch_app_token, client_secret=os.environ["TWITCH_CLIENT_SECRET"])
        refused_ids: set[str] = await sync_to_async(Player.get_not_allowed_ids)()

    except Exception as exc:  # pylint: disable=broad-except
        # we have to do this because aiohttp completely ignore exceptions raised in coroutines started by `on_startup`
        # so at least we log something
        logger.exception("Failed to initialize the Twitch click catchers")
        raise exc

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
                        user_id_str, x_relative, y_relative = get_data(raw_data)
                    except ValueError as exc:
                        logger.error(str(exc.args[0]), *exc.args[1:])
                        if len(exc.args) > 2:
                            refused_ids.add(exc.args[2])
                        continue

                    if user_id_str in refused_ids:
                        continue

                    try:
                        user_id = await validate_user_id(user_id_str)
                    except ValueError as exc:
                        logger.error(str(exc), user_id_str)
                        refused_ids.add(user_id_str)
                        continue

                    try:
                        username = await get_user_name(user_id, twitch_client)
                    except Exception as exc:  # pylint: disable=broad-except
                        logger.error("Failed to get username for user %s: %s", user_id, str(exc))
                        continue

                    x_absolute = int(x_relative * SCREEN_SIZE[0])
                    y_absolute = int(y_relative * SCREEN_SIZE[1])
                    target = get_click_target(x_absolute, y_absolute)
                    logger.info("%s clicked at on %s (%s, %s)", username, target, x_absolute, y_absolute)

                except Exception:  # pylint: disable=broad-except
                    logger.exception("Unhandled exception while trying to process WS message: %s", raw_data)


async def main() -> None:
    """Run the catch_clicks coroutine alone."""
    twitch_app_token = await get_twitch_app_token()
    await catch_clicks(twitch_app_token)


if __name__ == "__main__":
    asyncio.run(main())
