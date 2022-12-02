"""Twitch tools."""
import asyncio
import logging
import os
from asyncio import Queue
from typing import Optional, TypeAlias, cast

from twitchAPI.oauth import UserAuthenticator  # type: ignore[import]
from twitchAPI.twitch import Twitch  # type: ignore[import]
from twitchAPI.types import AuthScope  # type: ignore[import]
from twitchio import Channel  # type: ignore[import]
from twitchio.ext.commands import Bot  # type: ignore[import]

logger = logging.getLogger(__name__)


CHANEL_NAME = "twidi_angel"

ChatMessagesQueue: TypeAlias = Queue[str]


async def get_twitch_tokens() -> tuple[str, str]:
    """Get the Twitch token and refresh token.

    Returns
    -------
    tuple[str, str]
        The Twitch app token and the refresh token.

    """
    if not os.environ.get("TWITCH_CLIENT_ID"):
        raise RuntimeError("TWITCH_CLIENT_ID is not set. Please set it in .env or as an environment variable.")

    if not os.environ.get("TWITCH_CLIENT_SECRET"):
        raise RuntimeError("TWITCH_CLIENT_SECRET is not set. Please set it in .env or as an environment variable.")

    twitch = Twitch(os.environ["TWITCH_CLIENT_ID"], os.environ["TWITCH_CLIENT_SECRET"])
    auth = UserAuthenticator(twitch, [AuthScope.CHAT_EDIT, AuthScope.CHAT_READ], force_verify=False)
    return cast(tuple[str, str], await auth.authenticate())


class TwitchClient(Bot):
    """Our Twitch client to fetch users and send messages."""

    def __init__(self, token: str, refresh_token: str) -> None:
        """Initialize the Twitch client."""
        # noinspection InvisibleCharacter
        super().__init__(
            token=token,
            client_secret=os.environ["TWITCH_CLIENT_SECRET"],
            prefix=" ",
            nick=CHANEL_NAME,
            initial_channels=[CHANEL_NAME],
            loop=asyncio.get_running_loop(),
        )
        self._http._refresh_token = refresh_token  # pylint: disable=protected-access
        self.running_task: asyncio.Task[None] = asyncio.create_task(self.start(), name="twitch_client")
        self.channel: Optional[Channel] = None

    async def event_ready(self) -> None:
        """Create channel when the client is ready."""
        self.channel = self.get_channel(CHANEL_NAME)

    async def send_messages(self, queue: ChatMessagesQueue) -> None:
        """Send a message to the chat."""
        while True:
            if self.channel is None:
                await asyncio.sleep(1)
                continue
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1)
            except asyncio.TimeoutError:
                continue
            else:
                await self.channel.send(message)
                queue.task_done()


def get_twitch_client(token: str, refresh_token: str) -> TwitchClient:
    """Get a Twitch client.

    Parameters
    ----------
    token: str
        The Twitch token.
    refresh_token: str
        The Twitch refresh token.

    Returns
    -------
    TwitchClient
        The Twitch client.

    """
    try:
        return TwitchClient(token, refresh_token)
    except Exception as exc:  # pylint: disable=broad-except
        # we have to do this because aiohttp completely ignore exceptions raised in coroutines started by `on_startup`
        # so at least we log something
        logger.exception("Failed to initialize the Twitch client")
        raise exc


async def fetch_user_name(user_id: int, twitch_client: TwitchClient) -> str:
    """Get the username of a user from their ID.

    Parameters
    ----------
    user_id: int
        The ID of the user.
    twitch_client: TwitchClient
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


if __name__ == "__main__":
    from .. import django_setup  # noqa: F401  # pylint: disable=unused-import

    async def twitch_test() -> None:
        """Test the Twitch client."""
        token, refresh_token = await get_twitch_tokens()
        twitch_client = get_twitch_client(token, refresh_token)
        await asyncio.sleep(10)
        twitch_client.running_task.cancel()
        while not twitch_client.running_task.cancelled():
            await asyncio.sleep(0.01)

    asyncio.run(twitch_test())
