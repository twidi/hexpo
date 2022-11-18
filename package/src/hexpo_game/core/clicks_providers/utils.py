"""Utils functions to be used by the different clicks providers."""
import logging
import os
from typing import Awaitable, Callable, Optional, TypeAlias, cast

import aiohttp
from asgiref.sync import sync_to_async
from dotenv import load_dotenv
from twitchio import Client  # type: ignore[import]

from ... import django_setup  # noqa: F401  # pylint: disable=unused-import
from ..models import Player

logger = logging.getLogger(__name__)


ClickCallback: TypeAlias = Callable[[Player, float, float], Awaitable[None]]


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


async def get_twitch_client(twitch_app_token: str) -> Client:
    """Get a Twitch client.

    Parameters
    ----------
    twitch_app_token: str
        The Twitch app token.

    Returns
    -------
    Client
        The Twitch client.

    """
    try:
        return Client(token=twitch_app_token, client_secret=os.environ["TWITCH_CLIENT_SECRET"])
    except Exception as exc:  # pylint: disable=broad-except
        # we have to do this because aiohttp completely ignore exceptions raised in coroutines started by `on_startup`
        # so at least we log something
        logger.exception("Failed to initialize the Twitch click catchers")
        raise exc


async def init_refused_ids() -> set[str]:
    """Initialize the list of refused IDs."""
    return cast(set[str], await sync_to_async(Player.get_not_allowed_ids)())


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


async def get_player(user_id: int, twitch_client: Client) -> Player:
    """Get the player from their twitch ID.

    Parameters
    ----------
    user_id: int
        The ID of the user.
    twitch_client: Client
        The Twitch client to use.

    Returns
    -------
    Player
        The player we got or created for the given user ID.

    """
    player: Optional[Player]
    try:
        player = await Player.objects.aget(external_id=user_id)
    except Player.DoesNotExist:
        player = username = None
    else:
        username = player.name

    if player is None or not username:
        username = await fetch_user_name(user_id, twitch_client)
        if player is None:
            player = await Player.objects.acreate(external_id=user_id, name=username)
        else:
            player.name = username
            await player.asave(update_fields=["name"])  # type: ignore[attr-defined]

    return player


async def standalone_runner(catch_clicks: Callable[[str, ClickCallback], Awaitable[None]]) -> None:
    """Run the catch_clicks coroutine alone."""

    async def on_click(player: Player, x_relative: float, y_relative: float) -> None:
        """Display a message when a click is received."""
        logger.info("%s clicked at (%s, %s)", player.name, x_relative, y_relative)

    twitch_app_token = await get_twitch_app_token()
    await catch_clicks(twitch_app_token, on_click)


async def handle_click(
    user_id: str,
    x_relative: float,
    y_relative: float,
    twitch_client: Client,
    refused_ids: set[str],
    callback: ClickCallback,
) -> None:
    """Handle a click.

    Parameters
    ----------
    user_id: str
        The user_id of the user who clicked.
    x_relative: float
        The x coordinate of the click, relative to the screen size.
    y_relative: float
        The y coordinate of the click, relative to the screen size.
    twitch_client: Client
        The Twitch client to use to get the username.
    refused_ids: set[str]
        The set of refused user IDs.
    callback: ClickCallback
        The callback to call when a click from a valid user is received.

    """
    if user_id in refused_ids:
        return

    try:
        final_user_id = await validate_user_id(user_id)
    except ValueError as exc:
        logger.error(str(exc), user_id)
        refused_ids.add(user_id)
        return

    try:
        player = await get_player(final_user_id, twitch_client)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to get username for user %s: %s", user_id, str(exc))
        return

    await callback(player, x_relative, y_relative)
