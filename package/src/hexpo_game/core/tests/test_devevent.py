"""Tests integration for the `DevEvent`."""

import asyncio

import pytest
from asgiref.sync import sync_to_async
from asynctest import CoroutineMock, patch  # type: ignore[import]
from django.db.models import Sum

from hexpo_game.core.devevent import fetch_donations
from hexpo_game.core.models import Player
from hexpo_game.core.twitch import ChatMessagesQueue
from hexpo_game.core.types import GameMessageKind, GameMessagesQueue


@patch("aiohttp.ClientSession.get")
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_donations(mock: CoroutineMock) -> None:
    """
    Mock calling aiohttp HTTP request
    """
    chat_messages_queue: ChatMessagesQueue = asyncio.Queue()
    game_messages_queue: GameMessagesQueue = asyncio.Queue()

    donations = [
        {
            "id": "455845029492520965",
            "donation": {
                "id": "455768204816943973",
                "display_name": "Silvere Test",
                "amount_usd": 105,
                "converted_currency": "EUR",
                "converted_amount": 100,
                "created_at": "2022-12-13T20:15:40+00:00",
                "team_member_id": "487067726184058880",
                "comment": {"id": "455845021506363723", "text": "Ceci est un test"},
                "z_event_name": None,
            },
            "member": None,
        },
        {
            "id": "455845029492520981",
            "donation": {
                "id": "455768204816943990",
                "display_name": "Silvere Test",
                "amount_usd": 105,
                "converted_currency": "EUR",
                "converted_amount": 100,
                "created_at": "2022-12-13T20:41:54+00:00",
                "team_member_id": "487067726184058880",
                "comment": {"id": "455845021506363730", "text": "test"},
                "z_event_name": None,
            },
            "member": None,
        },
        {
            "id": "455845029492521658",
            "donation": {
                "id": "455768204816944711",
                "display_name": "existing_user",
                "amount_usd": 106,
                "converted_currency": "EUR",
                "converted_amount": 100,
                "created_at": "2022-12-14T14:28:32+00:00",
                "team_member_id": "490500326743478453",
                "comment": {"id": "455845021506364170", "text": "test 1"},
                "z_event_name": None,
            },
            "member": {
                "id": "490500326743478453",
                "user": {
                    "id": "342049851833454592",
                    "display_name": "Twidi_Angel",
                    "slug": "twidi-angel",
                    "is_live": False,
                    "currency": "EUR",
                },
            },
        },
        {
            "id": "455845029492521659",
            "donation": {
                "id": "455768204816944712",
                "display_name": "non_existing_user",
                "amount_usd": 106,
                "converted_currency": "EUR",
                "converted_amount": 100,
                "created_at": "2022-12-14T14:30:31+00:00",
                "team_member_id": "490500326743478453",
                "comment": {"id": "455845021506364171", "text": "test 2"},
                "z_event_name": None,
            },
            "member": {
                "id": "490500326743478453",
                "user": {
                    "id": "342049851833454592",
                    "display_name": "Twidi_Angel",
                    "slug": "twidi-angel",
                    "is_live": False,
                    "currency": "EUR",
                },
            },
        },
    ]
    mock.return_value.__aenter__.return_value.json = CoroutineMock(side_effect=lambda: donations)

    player = await Player.objects.acreate(external_id="foo", name="Existing_User")

    await fetch_donations(game_messages_queue, chat_messages_queue, max_loops=2, sleep_seconds=0)

    player_operations = await sync_to_async(lambda: list(player.extra_action_operations.all()))()
    assert len(player_operations) == 1
    assert await sync_to_async(lambda: player.extra_action_operations.aggregate(Sum("value"))["value__sum"])() == 1
    assert game_messages_queue.qsize() == 2
    assert chat_messages_queue.qsize() == 2
    game_message1 = game_messages_queue.get_nowait()
    game_messages_queue.task_done()
    game_message2 = game_messages_queue.get_nowait()
    game_messages_queue.task_done()
    chat_message1 = chat_messages_queue.get_nowait()
    chat_messages_queue.task_done()
    chat_message2 = chat_messages_queue.get_nowait()
    chat_messages_queue.task_done()
    assert game_message1.kind == GameMessageKind.DONATION
    assert game_message1.player_id == player.id
    assert game_message2.kind == GameMessageKind.DONATION
    assert game_message2.player_id is None
    assert chat_message1.startswith("@Existing_User ")
    assert chat_message2.startswith("non_existing_user ")

    donations.append(
        {
            "id": "555845029492521658",
            "donation": {
                "id": "555768204816944711",
                "display_name": "existing_user",
                "amount_usd": 106,
                "converted_currency": "EUR",
                "converted_amount": 150,
                "created_at": "2022-12-14T14:28:32+00:00",
                "team_member_id": "490500326743478453",
                "comment": {"id": "455845021506364170", "text": "test 1"},
                "z_event_name": None,
            },
            "member": {
                "id": "490500326743478453",
                "user": {
                    "id": "342049851833454592",
                    "display_name": "Twidi_Angel",
                    "slug": "twidi-angel",
                    "is_live": False,
                    "currency": "EUR",
                },
            },
        },
    )

    await fetch_donations(game_messages_queue, chat_messages_queue, max_loops=2, sleep_seconds=0)

    player_operations = await sync_to_async(lambda: list(player.extra_action_operations.all()))()
    assert len(player_operations) == 2
    assert await sync_to_async(lambda: player.extra_action_operations.aggregate(Sum("value"))["value__sum"])() == 2.5
    assert game_messages_queue.qsize() == 1
    assert chat_messages_queue.qsize() == 1
    game_message1 = game_messages_queue.get_nowait()
    chat_message1 = chat_messages_queue.get_nowait()
    game_messages_queue.task_done()
    chat_messages_queue.task_done()
    assert game_message1.kind == GameMessageKind.DONATION
    assert game_message1.player_id == player.id
    assert chat_message1.startswith("@Existing_User ")
