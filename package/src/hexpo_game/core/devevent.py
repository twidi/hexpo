"""Save donations from `LeDevEvent` as extra actions operations (1€ = 1PA)."""

import asyncio
import logging
from typing import NamedTuple, Optional

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

DONATIONS_URL = f"https://streamlabscharity.com/api/v1/teams/{TEAM_ID}/donations"

logger = logging.getLogger("hexpo_game.devevent")


class SavedDonation(NamedTuple):
    """Local saving of a donation."""

    id: str
    name: str
    amount: float
    is_via_member: bool


saved_donations: dict[str, SavedDonation] = {}


async def handle_donation(saved_donation: SavedDonation) -> Optional[GameMessage]:
    """Save the donation as an extra actions operation if it does not exist."""
    try:
        amount_human = int_or_float_as_str(saved_donation.amount)
        reason = f"#DevEvent {saved_donation.name.lower()} a donné {amount_human}€."
        chat_message = reason

        logger.warning("%s donated %s", saved_donation.name, amount_human)

        player = await Player.objects.filter(name__iexact=saved_donation.name).afirst()

        if player is not None:
            reason += " Et gagne autant de PA."
            chat_message = f"#DevEvent @{player.name}  a donné {amount_human}€. Et gagne autant de PA."
            player.extra_actions += saved_donation.amount
            await player.asave()

        await ExtraActionOperation.objects.acreate(
            player=player,
            value=saved_donation.amount,
            reason=reason,
            reference=f"{REFERENCE_KEY}-{saved_donation.id}",
        )

        return GameMessage(
            text=reason,
            kind=GameMessageKind.DEVEVENT,
            color=Color(0, 0, 0),
            player_id=None if player is None else player.id,
            chat_text=chat_message,
        )

    except Exception:  # pylint: disable=broad-except
        return None


async def fetch_donations(  # pylint: disable=too-many-locals, too-many-branches
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
                    id=operation.reference[len(REFERENCE_KEY) + 1 :],
                    name=operation.player.name,
                    amount=operation.value,
                    is_via_member=operation.player_id is not None,
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

    team_amount = team_member_amount = 0.0
    for donation in saved_donations.values():
        team_amount += donation.amount
        if donation.is_via_member:
            team_member_amount += donation.amount

    nb_loops = 0
    old_team_amount, old_team_member_amount = team_amount, team_member_amount
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(DONATIONS_URL) as resp:
                    entries = await resp.json()
                    for entry in entries:
                        try:
                            if (donation := entry.get("donation")) is None:
                                continue
                            if (donation_id := donation.get("id")) is None or donation_id in saved_donations:
                                continue
                            saved_donations[donation_id] = saved_donation = SavedDonation(
                                id=donation_id,
                                name=donation["display_name"].strip(),
                                amount=donation["converted_amount"] / 100,
                                is_via_member=((entry.get("member") or {}).get("user") or {}).get("id")
                                == TEAM_MEMBER_ID,
                            )
                            team_amount += saved_donation.amount
                            if not saved_donation.is_via_member:
                                continue
                            team_member_amount += saved_donation.amount
                            if (message := await handle_donation(saved_donation)) is None:
                                continue
                            if message.chat_text is not None:
                                await chat_messages_queue.put(message.chat_text)
                            await game_messages_queue.put(message)

                        except Exception:  # pylint: disable=broad-except
                            logger.exception("Error while handling donation %s", entry)

                if team_member_amount != old_team_member_amount:
                    await game_messages_queue.put(
                        GameMessage(
                            text=f"#DevEvent Vous avez donné {int_or_float_as_str(team_member_amount)}€ !",
                            kind=GameMessageKind.DEVEVENT,
                            color=Color(0, 0, 0),
                            player_id=None,
                        )
                    )
                    await chat_messages_queue.put(
                        f"#DevEvent Vous avez donné {int_or_float_as_str(team_member_amount)}€ ! "
                        f"(total des streamers: {int_or_float_as_str(team_amount)}€ )",
                    )

                elif team_amount != old_team_amount:
                    await game_messages_queue.put(
                        GameMessage(
                            text=f"#DevEvent Le total de dons est de {int_or_float_as_str(team_amount)}€.",
                            kind=GameMessageKind.DEVEVENT,
                            color=Color(0, 0, 0),
                            player_id=None,
                        )
                    )
                    await chat_messages_queue.put(
                        f"#DevEvent Le total de dons est de {int_or_float_as_str(team_amount)}€ "
                        f"(dont {int_or_float_as_str(team_member_amount)}€ par vous !)."
                    )

            except KeyboardInterrupt:
                break
            except Exception:  # pylint: disable=broad-except
                logger.exception("Error while fetching donations")

            old_team_amount = team_amount
            old_team_member_amount = team_member_amount

            nb_loops += 1
            if max_loops is not None and nb_loops >= max_loops:
                break
            await asyncio.sleep(sleep_seconds)
