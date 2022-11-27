"""Test the views of the game."""
from datetime import timedelta
from typing import Optional, cast

import pytest
import time_machine
from asgiref.sync import sync_to_async
from django.utils import timezone

from hexpo_game.core.constants import GameMode
from hexpo_game.core.grid import ConcreteGrid, Grid
from hexpo_game.core.models import Game, Player, PlayerInGame
from hexpo_game.core.types import Color
from hexpo_game.core.views import GameState, Message, MessageKind


async def make_game_state() -> GameState:
    """Make a game state."""
    nb_cols, nb_rows = Grid.compute_grid_size(20, 1 / 2)
    game = await Game.objects.acreate(
        mode=GameMode.FREE_NEIGHBOR,
        grid_nb_cols=nb_cols,
        grid_nb_rows=nb_rows,
        max_players_allowed=20,
        current_turn_end=timezone.now() + timedelta(minutes=10),
    )
    return cast(
        GameState, await sync_to_async(GameState)(game, ConcreteGrid(Grid(nb_cols, nb_rows), 5), game.started_at)
    )


async def make_player(external_id: int = 1, name: Optional[str] = None) -> Player:
    """Create a player."""
    return await Player.objects.acreate(
        external_id=external_id, name=f"Player {external_id}" if name is None else name
    )


async def make_player_in_game(game: Game, player: Player, col: int = 0, row: int = 0) -> PlayerInGame:
    """Create a player in game."""
    return await PlayerInGame.objects.acreate(
        game=game,
        player=player,
        started_turn=0,
        start_tile_col=col,
        start_tile_row=row,
        color=Color(0, 0, 0).as_hex,
        level=1,
    )


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_update_messages_nothing() -> None:
    """Test that the messages are not updated if there is no change."""
    game_state = await make_game_state()
    await game_state.update_messages()
    assert game_state.messages == []


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_update_messages_remove_old() -> None:
    """Test that old messages are removed."""
    game_state = await make_game_state()
    game_state.messages.append(
        Message(text="test1", kind=MessageKind.OTHER, display_until=timezone.now() - timedelta(seconds=10))
    )
    game_state.messages.append(
        Message(text="test2", kind=MessageKind.OTHER, display_until=timezone.now() - timedelta(seconds=1))
    )
    game_state.messages.append(
        message3 := Message(
            text="test3", kind=MessageKind.OTHER, display_until=timezone.now() + timedelta(seconds=10)
        )
    )
    game_state.messages.append(
        message4 := Message(
            text="test3", kind=MessageKind.OTHER, display_until=timezone.now() + timedelta(seconds=100)
        )
    )
    await game_state.update_messages()
    assert game_state.messages == [message3, message4]


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_update_messages_first_message() -> None:
    """Test a first message."""
    game_state = await make_game_state()
    player_in_game = await make_player_in_game(game_state.game, await make_player())
    with time_machine.travel(
        timezone.now(), tick=False
    ):  # freezegun does not work well with timezone aware datetimes
        await game_state.update_messages()
        expected_message = Message(
            text=f"{player_in_game.player.name} est arrivé en A‑1",
            kind=MessageKind.NEW_PLAYER,
            display_until=timezone.now() + timedelta(seconds=15),
            color=Color(0, 0, 0),
        )
    assert game_state.messages == [expected_message]


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_update_messages_new_messages() -> None:
    """Test adding messages."""
    game_state = await make_game_state()
    player_in_game = await make_player_in_game(game_state.game, (player := await make_player()))
    with time_machine.travel(timezone.now(), tick=False):
        await game_state.update_messages()
        expected_message_1 = Message(
            text=f"{player_in_game.player.name} est arrivé en A‑1",
            kind=MessageKind.NEW_PLAYER,
            display_until=timezone.now() + timedelta(seconds=15),
            color=Color(0, 0, 0),
        )
    assert game_state.messages == [expected_message_1]
    player_in_game2 = await make_player_in_game(game_state.game, await make_player(2), col=1, row=1)
    with time_machine.travel(timezone.now(), tick=False):
        await game_state.update_messages()
        expected_message_2 = Message(
            text=f"{player_in_game2.player.name} est arrivé en B‑2",
            kind=MessageKind.NEW_PLAYER,
            display_until=timezone.now() + timedelta(seconds=15),
            color=Color(0, 0, 0),
        )
    assert game_state.messages == [expected_message_1, expected_message_2]
    await player_in_game.adie(killer=player_in_game2)
    player_in_game3 = await make_player_in_game(game_state.game, await make_player(3), col=2, row=2)
    await player_in_game2.adie(killer=player_in_game3)
    player_in_game1_bis = await make_player_in_game(game_state.game, player, col=3, row=3)
    # here we check the order, not the exactness of the dates, it's why we don't mock the date
    await game_state.update_messages()
    expected_message_3_msg = f"{player_in_game.player.name} a été tué par {player_in_game2.player.name}"
    expected_message_4_msg = f"{player_in_game3.player.name} est arrivé en C‑3"
    expected_message_5_msg = f"{player_in_game2.player.name} a été tué par {player_in_game3.player.name}"
    expected_message_6_msg = f"{player_in_game1_bis.player.name} est revenu en D‑4"
    assert [(message.kind, message.text) for message in game_state.messages] == [
        (expected_message_1.kind, expected_message_1.text),
        (expected_message_2.kind, expected_message_2.text),
        (MessageKind.DEATH, expected_message_3_msg),
        (MessageKind.NEW_PLAYER, expected_message_4_msg),
        (MessageKind.DEATH, expected_message_5_msg),
        (MessageKind.RESPAWN, expected_message_6_msg),
    ]
