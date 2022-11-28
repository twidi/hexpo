"""Utils functions to be used by the different clicks providers."""
import logging
from typing import Awaitable, Callable, Optional, TypeAlias, cast

from asgiref.sync import sync_to_async

from ... import django_setup  # noqa: F401  # pylint: disable=unused-import
from ..models import Player
from ..twitch import ChatMessagesQueue, TwitchClient, fetch_user_name

logger = logging.getLogger(__name__)


ClickCallback: TypeAlias = Callable[[Player, float, float], Awaitable[None]]


async def init_refused_ids() -> set[str]:
    """Initialize the list of refused IDs."""
    return cast(set[str], await sync_to_async(Player.get_not_allowed_ids)())


class AnonymousUser(ValueError):
    """Raised when the user is anonymous."""


class OpaqueUser(ValueError):
    """Raised when the user id is opaque."""


class InvalidUser(ValueError):
    """Raised when the user is invalid."""


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
    AnonymousUser
        If the user is anonymous (the id starts with a "A").
    OpaqueUser
        If the user ID is opaque (the id starts with a "U": they didn't accept to share their ID).
    InvalidUser
        If the user id is not a number.

    """
    if user_id.startswith("A"):
        raise AnonymousUser("User %s is not logged in on Twitch.")
    if user_id.startswith("U"):
        raise OpaqueUser("User %s did no accept to share its ID")
    try:
        return int(user_id)
    except ValueError:
        raise InvalidUser("User ID %s is not an integer") from None


async def get_player(user_id: int, twitch_client: TwitchClient) -> Player:
    """Get the player from their twitch ID.

    Parameters
    ----------
    user_id: int
        The ID of the user.
    twitch_client: TwitchClient
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

    if player is None or not username or username == "Twidi_Angel":
        username = await fetch_user_name(user_id, twitch_client)
        if player is None:
            player = await Player.objects.acreate(external_id=user_id, name=username)
        else:
            player.name = username
            await player.asave(update_fields=["name"])  # type: ignore[attr-defined]

    return player


async def handle_click(
    user_id: str,
    x_relative: float,
    y_relative: float,
    twitch_client: TwitchClient,
    chats_messages_queue: ChatMessagesQueue,
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
    twitch_client: TwitchClient
        The Twitch client to use to get the username.
    chats_messages_queue: ChatMessagesQueue
        The queue to use to send messages to the chat.
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
        if isinstance(exc, AnonymousUser):
            await chats_messages_queue.put(
                "A toi, joueur inconnu et non connecté à Twitch, qui vient de cliquer sur le stream, "
                "si tu veux jouer tu dois te connecter à Twitch "
                "puis suivre les instructions affichées en haut du stream !"
            )
        elif isinstance(exc, OpaqueUser):
            await chats_messages_queue.put(
                "A toi, joueur inconnu, qui vient de cliquer sur le stream, "
                "si tu veux jouer tu dois suivre les instructions affichées en haut du stream !"
            )
        logger.error(str(exc), user_id)
        refused_ids.add(user_id)
        return

    try:
        player = await get_player(final_user_id, twitch_client)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to get username for user %s: %s", user_id, str(exc))
        return

    if not player.allowed:
        logger.warning("Player %s is not allowed to play", player.name)
        return

    await callback(player, x_relative, y_relative)
