"""Save donations from `LeDevEvent` as extra actions operations (1€ = 1PA)."""

import asyncio
import logging
from typing import Any, NamedTuple, Optional

import aiohttp
from asgiref.sync import sync_to_async

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .models import ExtraActionOperation, Player
from .twitch import ChatMessagesQueue
from .types import Color, GameMessage, GameMessageKind, GameMessagesQueue
from .views import int_or_float_as_str

TEAM_ID = "487066378935865344"
TEAM_MEMBER_ID = "342049851833454592"
REFERENCE_KEY = "devevent2022"

MESSAGE_COLOR = Color.from_hex("#ef65ef")

DONATIONS_URL = f"https://streamlabscharity.com/api/v1/teams/{TEAM_ID}/donations"

logger = logging.getLogger("hexpo_game.devevent")


class SavedDonation(NamedTuple):
    """Local saving of a donation."""

    name: str
    amount: float


saved_donations: dict[str, SavedDonation] = {}


async def handle_donation(donation: dict[str, Any]) -> Optional[GameMessage]:
    """Save the donation as an extra actions operation if it does not exist."""
    try:
        if donation["id"] in saved_donations:
            return None

        saved_donations[donation["id"]] = saved_donation = SavedDonation(
            name=donation["display_name"].strip(), amount=donation["converted_amount"] / 100
        )
        amount_human = int_or_float_as_str(saved_donation.amount)
        reason = f"{saved_donation.name.lower()} a donné {amount_human}€."
        chat_message = reason

        logger.warning("%s donated %s", saved_donation.name, amount_human)

        player = await Player.objects.filter(name__iexact=saved_donation.name).afirst()

        if player is not None:
            reason += " Et gagne autant de PA."
            chat_message = f"@{player.name}  a donné {amount_human}€. Et gagne autant de PA."
            player.extra_actions += saved_donation.amount
            await player.asave()

        await ExtraActionOperation.objects.acreate(
            player=player, value=saved_donation.amount, reason=reason, reference=f"{REFERENCE_KEY}-{donation['id']}"
        )

        return GameMessage(
            text=reason,
            kind=GameMessageKind.DONATION,
            color=MESSAGE_COLOR,
            player_id=None if player is None else player.id,
            chat_text=chat_message,
        )

    except Exception:  # pylint: disable=broad-except
        return None


async def fetch_donations(
    game_messages_queue: GameMessagesQueue,
    chat_messages_queue: ChatMessagesQueue,
    max_loops: Optional[int] = None,
    sleep_seconds: float = 10,
) -> None:
    """Fetch and update donations."""
    if not saved_donations:
        saved_donations.update(
            {
                operation.reference[len(REFERENCE_KEY) + 1 :]: SavedDonation(
                    name=operation.player.name, amount=operation.value
                )
                for operation in await sync_to_async(
                    lambda: list(
                        ExtraActionOperation.objects.filter(reference__startswith=f"{REFERENCE_KEY}-").select_related(
                            "player"
                        )
                    )
                )()
            }
        )

    nb_loops = 0
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(DONATIONS_URL) as resp:
                    entries = await resp.json()
                    for entry in entries:
                        if ((entry.get("member") or {}).get("user") or {}).get("id") != TEAM_MEMBER_ID:
                            continue
                        if donation := entry.get("donation"):
                            if (message := await handle_donation(donation)) is None:
                                continue
                            if message.chat_text is not None:
                                await chat_messages_queue.put(message.chat_text)
                            await game_messages_queue.put(message)

            except KeyboardInterrupt:
                break
            except Exception:  # pylint: disable=broad-except
                pass
            nb_loops += 1
            if max_loops is not None and nb_loops >= max_loops:
                break
            await asyncio.sleep(sleep_seconds)
