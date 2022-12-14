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
from twitchio.ext import commands  # type: ignore[import]
from twitchio.ext.commands import Bot, CommandNotFound, Context  # type: ignore[import]

from hexpo_game.core.constants import GAME_MODE_CONFIGS, GameMode, GameStep

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

    def __init__(self, token: str, refresh_token: str, game_mode: GameMode) -> None:
        """Initialize the Twitch client."""
        super().__init__(
            token=token,
            client_secret=os.environ["TWITCH_CLIENT_SECRET"],
            prefix="!",
            nick=CHANEL_NAME,
            initial_channels=[CHANEL_NAME],
            loop=asyncio.get_running_loop(),
        )
        self._http._refresh_token = refresh_token  # pylint: disable=protected-access
        self.running_task: asyncio.Task[None] = asyncio.create_task(self.start(), name="twitch_client")
        self.channel: Optional[Channel] = None
        self.game_mode = game_mode

    async def event_ready(self) -> None:
        """Create channel when the client is ready."""
        self.channel = self.get_channel(CHANEL_NAME)

    async def send_messages(self, queue: ChatMessagesQueue) -> None:
        """Send messages from the queue to the chat."""
        while True:
            if self.channel is None:
                await asyncio.sleep(1)
                continue
            # pylint: disable=duplicate-code
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1)
            except asyncio.TimeoutError:
                continue
            else:
                await self.channel.send(message)
                queue.task_done()

    @commands.command()  # type: ignore[misc]
    async def game(self, ctx: Context) -> None:
        """Change the game."""
        if self.game_mode == GameMode.TURN_BY_TURN:
            await ctx.send(
                "[1/4] "
                "Bienvenue dans le jeu 'Hexpocalypse Later'. "
                "Clique sur l'extension ?? droite du stream, puis sur 'G??rez vos acc??s' et partage ton identifiant ! "
                f"Ensuite attend l'??tape (en haut ?? gauche) '{GameStep.WAITING_FOR_PLAYERS.label}' pour commencer. "
                "Tu pourras alors cliquer sur le stream pour commencer ton territoire."
            )
            await asyncio.sleep(1)
            await ctx.send(
                "[2/4] "
                "C'est un jeu de strat??gie en tour par tour. ?? chaque tour tu as une ou plusieurs actions "
                "disponibles pour attaquer un adversaire, d??fendre ton territoire, ou l'agrandir. "
                f"Tu peux aussi banquer {GAME_MODE_CONFIGS[GameMode.TURN_BY_TURN].bank_value * 100:.0f}% "
                f"d'une action pour l'utiliser plus tard."
            )
            await asyncio.sleep(1)
            await ctx.send(
                "[3/4] "
                "Une case d??marre ?? max 20 PV (sur un total max de 100) et chaque action en ajoute/retire max 20, "
                "mais ce nombre n'est affich?? nul part, sauf quand une action est ex??cut??e: il faut avoir l'oeil. "
            )
            await asyncio.sleep(1)
            await ctx.send(
                "[4/4] "
                "Note que ce '20' est un max car ??a d??pend de l'efficacit?? de ton action ! Plus elle sera confirm??e "
                "t??t dans le tour, plus elle sera efficace, sinon elle pourra perdre jusqu'?? 50% de son efficacit??."
            )
        else:
            await ctx.send(
                "[1/3] "
                "Bienvenue dans la version 'Faster' du jeu 'Hexpocalypse Later'. "
                "Clique sur l'extension ?? droite du stream, puis sur 'G??rez vos acc??s' et partage ton identifiant ! "
                "Ensuite clique sur le stream et cr??e ton territoire en cliquant a c??t?? d'une de tes pr??c??dentes cases."
            )
            await asyncio.sleep(1)
            await ctx.send(
                "[2/3] "
                "La latence du stream fait qu'il y a un d??lai entre le clic et l'affichage, c'est normal. "
                "Pendant tes 30 premi??res secondes (ou max 10 cases), tu as un rond au centre de tes cases, "
                "??a sert ?? te rep??rer, et en plus tu es invincible!."
            )
            await asyncio.sleep(1)
            await ctx.send(
                "[3/3] "
                "Ensuite, si ta derni??re case est prise, tu devras attendre 10 secondes avant de respawn "
                "(la latence peut rendre ce d??lai plus long). "
                "Une version plus strat??gique (et donc plus lente) est en cours d??velopement, "
                "n'h??site pas ?? follow pour suivre l'??volution et savoir quand elle sera disponible!"
            )

    async def event_command_error(self, context: Context, error: Exception) -> None:
        """Ignore CommandNotFound errors."""
        if not isinstance(error, CommandNotFound):
            await super().event_command_error(context, error)


def get_twitch_client(token: str, refresh_token: str, game_mode: GameMode) -> TwitchClient:
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
        return TwitchClient(token, refresh_token, game_mode)
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
