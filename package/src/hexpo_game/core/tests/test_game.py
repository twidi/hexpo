"""Tests for the grid package."""
# pylint: disable=too-many-lines
import asyncio
from datetime import timedelta
from time import time
from typing import Optional, Sequence, Set, cast

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from hexpo_game.core.constants import (
    ActionFailureReason,
    ActionState,
    ActionType,
    ButtonToAction,
    ClickTarget,
    GameMode,
    GameStep,
)
from hexpo_game.core.game import ClicksQueue, GameLoop, PlayerClick, aplay_turn
from hexpo_game.core.grid import Grid
from hexpo_game.core.models import Action, Game, OccupiedTile, Player, PlayerInGame
from hexpo_game.core.twitch import ChatMessagesQueue
from hexpo_game.core.types import Color, GameMessageKind, GameMessagesQueue, Tile


async def make_game(mode: GameMode = GameMode.FREE_NEIGHBOR) -> Game:
    """Create a game in the given mode."""
    nb_cols, nb_rows = Grid.compute_grid_size(20, 1 / 2)
    return await Game.objects.acreate(
        mode=mode,
        grid_nb_cols=nb_cols,
        grid_nb_rows=nb_rows,
        current_turn_step_end=timezone.now() + timedelta(minutes=10),
    )


async def make_turn_game() -> Game:
    """Create a turn game."""
    return await make_game(mode=GameMode.TURN_BY_TURN)


async def make_player(external_id: int = 1) -> Player:
    """Create a player."""
    return await Player.objects.acreate(external_id=external_id, name=f"Player {external_id}")


async def make_player_in_game(
    game: Game, player: Player, occupied_tiles: Optional[Sequence[Tile]] = None, level: int = 1
) -> PlayerInGame:
    """Create a player in game."""
    player_in_game = await PlayerInGame.objects.acreate(
        game=game,
        player=player,
        started_turn=0,
        start_tile_col=occupied_tiles[0].col if occupied_tiles else None,
        start_tile_row=occupied_tiles[0].row if occupied_tiles else None,
        color=Color(0, 0, 0).as_hex,
        level=level,
        first_in_game_for_player=True,
    )
    for tile in occupied_tiles or []:
        # pylint: disable=duplicate-code
        await OccupiedTile.objects.aupdate_or_create(
            game=game,
            col=tile.col,
            row=tile.row,
            defaults=dict(  # noqa: C408
                player_in_game=player_in_game,
                level=game.config.tile_start_level,
            ),
        )
        await Action.objects.acreate(
            game=game,
            player_in_game=player_in_game,
            turn=game.current_turn,
            action_type=ActionType.GROW,
            tile_col=tile.col,
            tile_row=tile.row,
            confirmed_at=timezone.now(),
            state=ActionState.SUCCESS,
        )

    return player_in_game


async def make_game_and_player(
    first_tile: Optional[Tile] = None, game_mode: GameMode = GameMode.FREE_NEIGHBOR, player_level: int = 1
) -> tuple[Game, Player, PlayerInGame]:
    """Make a game and a player in it."""
    game = await make_game(mode=game_mode)
    player = await make_player()
    player_in_game = await make_player_in_game(
        game, player, None if first_tile is None else [first_tile], player_level
    )
    return game, player, player_in_game


async def make_turn_game_and_player(first_tile: Tile, player_level: int = 1) -> tuple[Game, Player, PlayerInGame]:
    """Make a turn game and a player in it."""
    return await make_game_and_player(first_tile, GameMode.TURN_BY_TURN, player_level)


def save_action(  # pylint: disable=too-many-return-statements,too-many-branches
    player: Player, game: Game, tile: Optional[Tile], action_type: ActionType = ActionType.GROW, efficiency: float = 1
) -> Optional[Action]:
    """Save the player action if they clicked one a tile."""
    if game.config.multi_steps:
        # make player enter the game
        GameLoop.step_waiting_for_players_handle_click(
            PlayerClick(player, ClickTarget.MAP, tile), game, get_grid(game)
        )
        # make player click the button
        action_to_button = {action_type: target for target, action_type in ButtonToAction.items()}
        action = GameLoop.step_collecting_actions_handle_click_multi_steps(
            PlayerClick(player, action_to_button[action_type], None), game
        )
        # make player click the tile if any
        if action is not None and tile is not None:
            action = GameLoop.step_collecting_actions_handle_click_multi_steps(
                PlayerClick(player, ClickTarget.MAP, tile), game
            )
        # then make the player confirm the action
        if action is not None:
            action = GameLoop.step_collecting_actions_handle_click_multi_steps(
                PlayerClick(player, ClickTarget.BTN_CONFIRM, None), game
            )

    else:
        player_click = PlayerClick(player, ClickTarget.MAP, tile)
        action = GameLoop.step_collecting_actions_handle_click_single_step(player_click, game)

    if action is not None and action.efficiency != efficiency:
        action.efficiency = efficiency
        action.save()

    return action


async def asave_action(
    player: Player,
    game: Game,
    tile: Optional[Tile],
    action_type: ActionType = ActionType.GROW,
    efficiency: float = 1.0,
) -> Optional[Action]:
    """Save the player action if they clicked one a tile."""
    return cast(Optional[Action], await sync_to_async(save_action)(player, game, tile, action_type, efficiency))


def get_grid(game: Game) -> Grid:
    """Get the grid of the game."""
    return Grid(game.grid_nb_cols, game.grid_nb_rows)


def get_occupied_tiles(player_in_game: PlayerInGame) -> Set[Tile]:
    """Get the tiles occupied by the player in game."""
    return {Tile(col, row) for col, row in player_in_game.occupiedtile_set.values_list("col", "row")}


def get_actions_tiles(player_in_game: PlayerInGame) -> Set[Tile]:
    """Get the tiles the player tries to occupy in game."""
    return {
        Tile(cast(int, col), cast(int, row))
        for col, row in player_in_game.action_set.values_list("tile_col", "tile_row")
    }


async def assert_has_tiles(player_in_game: PlayerInGame, tiles: Sequence[Tile]) -> None:
    """Assert the player has the given tiles."""
    __tracebackhide__ = True  # pylint: disable=unused-variable
    occupied_tiles = await sync_to_async(get_occupied_tiles)(player_in_game)
    assert set(tiles) == occupied_tiles


async def assert_has_actions(player_in_game: PlayerInGame, tiles: Sequence[Tile]) -> None:
    """Assert the player has the actions on the given tiles."""
    __tracebackhide__ = True  # pylint: disable=unused-variable
    actions_tiles = await sync_to_async(get_actions_tiles)(player_in_game)
    assert set(tiles) == actions_tiles


async def assert_death(player_in_game: PlayerInGame, killed: bool, killed_by_id: Optional[int] = None) -> None:
    """Assert the player is dead or not."""
    __tracebackhide__ = True  # pylint: disable=unused-variable
    await player_in_game.arefresh_from_db()

    # any other way to load a fk in async ?
    await sync_to_async(getattr)(player_in_game, "player")

    assert (player_in_game.ended_turn is not None) == killed
    assert (player_in_game.dead_at is not None) == killed
    assert player_in_game.killed_by_id == killed_by_id


async def assert_action_state(
    action: Action, state: ActionState, failure_reason: Optional[ActionFailureReason] = None
) -> None:
    """Assert the player is dead or not."""
    __tracebackhide__ = True  # pylint: disable=unused-variable
    await action.arefresh_from_db()
    assert action.state == state
    assert action.failure_reason == failure_reason


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_new_player():
    """Test that a new player can click on a tile."""
    game = await make_game()
    player = await make_player()

    assert await game.playeringame_set.acount() == 0
    assert await game.occupiedtile_set.acount() == 0

    assert (action := await asave_action(player, game, Tile(0, 0))) is not None

    assert (player_in_game := action.player_in_game).player_id == player.id

    await aplay_turn(game, get_grid(game))

    await assert_has_actions(player_in_game, [Tile(0, 0)])
    await assert_has_tiles(player_in_game, [Tile(0, 0)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_no_tile():
    """Test that a player cannot click on a tile if there is no tile."""
    game = await make_game()
    player = await make_player()

    assert (await asave_action(player, game, None)) is None

    assert await game.playeringame_set.acount() == 0
    assert await game.occupiedtile_set.acount() == 0
    assert await game.action_set.acount() == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_free_tile():
    """Test that an existing player can click on a free tile."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 1))

    await assert_has_actions(player_in_game, [Tile(0, 1)])
    await assert_has_tiles(player_in_game, [Tile(0, 1)])

    await game.anext_turn()
    assert (action := await asave_action(player, game, Tile(0, 0))) is not None

    assert action.player_in_game_id == player_in_game.id

    await aplay_turn(game, get_grid(game))

    await assert_action_state(action, ActionState.SUCCESS)
    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(0, 1)])
    await assert_has_tiles(player_in_game, [Tile(0, 0), Tile(0, 1)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_non_neighbor_tile_in_free_neighbor_mode():
    """Test that a player cannot click on an invalid tile in FREE_NEIGHBOR mode."""
    game, player, player_in_game = await make_game_and_player(Tile(1, 1))

    await game.anext_turn()
    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game))

    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_NO_NEIGHBOR)
    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(1, 1)])
    await assert_has_tiles(player_in_game, [Tile(1, 1)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_non_neighbor_tile_in_free_full_mode():
    """Test that a player cannot click on an invalid tile in FREE_FULL mode."""
    game, player, player_in_game = await make_game_and_player(Tile(1, 1), game_mode=GameMode.FREE_FULL)

    await game.anext_turn()
    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game))

    await assert_action_state(action, ActionState.SUCCESS)
    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(1, 1)])
    await assert_has_tiles(player_in_game, [Tile(0, 0), Tile(1, 1)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_self_occupied_tile():
    """Test that a player cannot click on a tile occupied by themselves."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 0))

    await game.anext_turn()
    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game))

    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_SELF)
    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(0, 0)])
    await assert_has_tiles(player_in_game, [Tile(0, 0)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_protected_tile():
    """Test that a player cannot click on a protected tile."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 0))
    player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(0, 1)])

    await game.anext_turn()
    assert (action := await asave_action(player, game, Tile(0, 1))) is not None
    await aplay_turn(game, get_grid(game))

    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_PROTECTED)

    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(0, 1)])
    await assert_has_tiles(player_in_game, [Tile(0, 0)])
    await assert_death(player_in_game, False)

    await assert_has_actions(player_in_game2, [Tile(0, 1)])
    await assert_has_tiles(player_in_game2, [Tile(0, 1)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_tile_occupied_by_other():
    """Test that a player can click on a tile (among others) occupied by another player."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 1))
    player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(0, 0), Tile(1, 0)])

    await assert_has_actions(player_in_game, [Tile(0, 1)])
    await assert_has_tiles(player_in_game, [Tile(0, 1)])
    await assert_has_actions(player_in_game2, [Tile(0, 0), Tile(1, 0)])
    await assert_has_tiles(player_in_game2, [Tile(0, 0), Tile(1, 0)])

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game))

    await assert_action_state(action, ActionState.SUCCESS)

    await assert_has_actions(player_in_game, [Tile(0, 1), Tile(0, 0)])
    await assert_has_tiles(player_in_game, [Tile(0, 1), Tile(0, 0)])

    await assert_has_actions(player_in_game2, [Tile(0, 0), Tile(1, 0)])
    await assert_has_tiles(player_in_game2, [Tile(1, 0)])
    await assert_death(player_in_game2, False)
    assert await PlayerInGame.objects.filter(player_id=player_in_game2.player_id).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_tile_last_occupied_by_other():
    """Test that a player can click on the last tile occupied by another player."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 1))
    player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(0, 0)])

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game))

    await assert_action_state(action, ActionState.SUCCESS)

    await assert_has_actions(player_in_game, [Tile(0, 1), Tile(0, 0)])
    await assert_has_tiles(player_in_game, [Tile(0, 1), Tile(0, 0)])

    await assert_has_actions(player_in_game2, [Tile(0, 0)])
    await assert_has_tiles(player_in_game2, [])
    await assert_death(player_in_game2, True, player_in_game.id)
    assert await PlayerInGame.objects.filter(player_id=player_in_game2.player_id).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_tile_after_recent_death():
    """Test that a player cannot click on a tile if recently dead."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 0))
    player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(1, 0)])

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    await asave_action(player_in_game2.player, game, Tile(0, 0))
    await aplay_turn(game, grid := get_grid(game))
    await assert_death(player_in_game, True, player_in_game2.id)

    await game.anext_turn()
    assert await asave_action(player, game, Tile(0, 1)) is None
    await aplay_turn(game, grid)

    await assert_has_actions(player_in_game, [Tile(0, 0)])
    await assert_has_tiles(player_in_game, [])
    await assert_death(player_in_game, True, player_in_game2.id)
    assert await PlayerInGame.objects.filter(player=player).acount() == 1

    await assert_has_actions(player_in_game2, [Tile(1, 0), Tile(0, 0)])
    await assert_has_tiles(player_in_game2, [Tile(1, 0), Tile(0, 0)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_tile_after_not_recent_death():
    """Test that a player can click on a tile if dead but not recently."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 0))
    player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(1, 0)])

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    await asave_action(player_in_game2.player, game, Tile(0, 0))
    await aplay_turn(game, grid := get_grid(game))
    await assert_death(player_in_game, True, player_in_game2.id)

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    assert (action := await asave_action(player, game, Tile(0, 1))) is not None
    await aplay_turn(game, grid)

    await assert_action_state(action, ActionState.SUCCESS)

    await assert_has_actions(player_in_game, [Tile(0, 0)])
    await assert_has_tiles(player_in_game, [])
    await assert_death(player_in_game, True, player_in_game2.id)

    await assert_has_actions(player_in_game2, [Tile(1, 0), Tile(0, 0)])
    await assert_has_tiles(player_in_game2, [Tile(1, 0), Tile(0, 0)])

    player_in_game_new = await sync_to_async(lambda action: action.player_in_game)(action)
    assert player_in_game_new.id != player_in_game.id
    assert player_in_game_new.player_id == player_in_game.player_id
    await assert_has_actions(player_in_game_new, [Tile(0, 1)])
    await assert_has_tiles(player_in_game_new, [Tile(0, 1)])
    await assert_death(player_in_game_new, False)

    assert await PlayerInGame.objects.filter(player=player).acount() == 2


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_die_during_a_turn():
    """Test that actions of a player dead during a turn are ignored."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 0), player_level=2)
    player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(1, 0)], level=2)

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    assert (action_1 := await asave_action(player, game, Tile(0, 1))) is not None
    assert (action_2 := await asave_action(player_in_game2.player, game, Tile(0, 0))) is not None
    assert (action_3 := await asave_action(player_in_game2.player, game, Tile(0, 1))) is not None
    assert (action_4 := await asave_action(player, game, Tile(1, 1))) is not None

    await aplay_turn(game, get_grid(game))

    await assert_action_state(action_1, ActionState.SUCCESS)
    await assert_action_state(action_2, ActionState.SUCCESS)
    await assert_action_state(action_3, ActionState.SUCCESS)
    await assert_action_state(action_4, ActionState.FAILURE, ActionFailureReason.DEAD)

    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(0, 1), Tile(1, 1)])
    await assert_has_tiles(player_in_game, [])
    await assert_death(player_in_game, True, player_in_game2.id)

    await assert_has_actions(player_in_game2, [Tile(1, 0), Tile(0, 0), Tile(0, 1)])
    await assert_has_tiles(player_in_game2, [Tile(1, 0), Tile(0, 0), Tile(0, 1)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_first_click_on_protected():
    """Test that a player can click on a protected tile on the first turn."""
    game, _, player_in_game = await make_game_and_player(Tile(0, 0))
    await aplay_turn(game, grid := get_grid(game))

    player_in_game2 = await make_player_in_game(game, await make_player(2), [])

    await game.anext_turn()
    assert (action := await asave_action(player_in_game2.player, game, Tile(0, 0))) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_PROTECTED)

    await assert_has_actions(player_in_game, [Tile(0, 0)])
    await assert_has_tiles(player_in_game, [Tile(0, 0)])
    await assert_death(player_in_game, False)
    await assert_has_actions(player_in_game2, [Tile(0, 0)])
    await assert_has_tiles(player_in_game2, [])
    await assert_death(player_in_game2, False)

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    assert (action := await asave_action(player_in_game2.player, game, Tile(0, 0))) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.SUCCESS)

    await assert_has_actions(player_in_game, [Tile(0, 0)])
    await assert_has_tiles(player_in_game, [])
    await assert_death(player_in_game, True, player_in_game2.id)
    await assert_has_actions(player_in_game2, [Tile(0, 0), Tile(0, 0)])
    await assert_has_tiles(player_in_game2, [Tile(0, 0)])
    await assert_death(player_in_game2, False)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_cannot_use_more_than_allowed_actions():
    """Test that a player cannot confirm more actions than allowed."""
    game, _, player_in_game = await make_game_and_player(Tile(0, 0))
    await aplay_turn(game, get_grid(game))
    await game.anext_turn()

    assert await asave_action(player_in_game.player, game, Tile(0, 1)) is not None
    assert await asave_action(player_in_game.player, game, Tile(0, 0)) is None

    player_in_game.level += 1
    await player_in_game.asave()
    assert await asave_action(player_in_game.player, game, Tile(0, 0)) is not None
    assert await asave_action(player_in_game.player, game, Tile(0, 0)) is None

    player_in_game.banked_actions = 0.5
    await player_in_game.asave()
    assert await asave_action(player_in_game.player, game, Tile(0, 0)) is None

    player_in_game.banked_actions = 1.99999
    await player_in_game.asave()
    assert await asave_action(player_in_game.player, game, Tile(0, 0)) is not None
    assert await asave_action(player_in_game.player, game, Tile(0, 0)) is None

    player_in_game.banked_actions = 2.0001
    await player_in_game.asave()
    assert await asave_action(player_in_game.player, game, Tile(0, 0)) is not None
    assert await asave_action(player_in_game.player, game, Tile(0, 0)) is None


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_cannot_attack_self_tile():
    """Test that a player cannot attack a protected tile of its own in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    await aplay_turn(game, grid := get_grid(game))
    await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(0, 0), ActionType.ATTACK, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.ATTACK_SELF)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_cannot_attack_empty_tile():
    """Test that a player cannot attack an empty tile in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    await aplay_turn(game, grid := get_grid(game))
    await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(1, 1), ActionType.ATTACK, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.ATTACK_EMPTY)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_cannot_attack_other_protected_tile():
    """Test that a player cannot attack a protected tile of another player in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    await make_player_in_game(game, await make_player(2), [Tile(0, 1)])
    await aplay_turn(game, grid := get_grid(game))
    await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(0, 1), ActionType.ATTACK, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.ATTACK_PROTECTED)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_can_attack():
    """Test that a player can attack a tile in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(0, 1)])
    await aplay_turn(game, grid := get_grid(game))

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(0, 1), ActionType.ATTACK, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.SUCCESS)
    assert (
        await game.occupiedtile_set.aget(col=0, row=1)
    ).level == game.config.tile_start_level - game.config.attack_damage * 0.6
    await assert_has_tiles(player_in_game2, [Tile(0, 1)])
    await assert_death(player_in_game2, False)

    await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(0, 1), ActionType.ATTACK, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.SUCCESS)
    assert (await game.occupiedtile_set.filter(col=0, row=1).afirst()) is None
    await assert_has_tiles(player_in_game2, [])
    await assert_death(player_in_game2, True, player_in_game.id)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_farther_attack_is_less_efficient():
    """Test that attacking a far tile is less efficient than a near one in turn mode"""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    far_tile = Tile(game.grid_nb_cols - 1, game.grid_nb_rows - 1)
    await make_player_in_game(game, await make_player(2), [far_tile])
    await aplay_turn(game, grid := get_grid(game))

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, far_tile, ActionType.ATTACK, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.SUCCESS)
    assert (
        await game.occupiedtile_set.aget(col=far_tile.col, row=far_tile.row)
    ).level == game.config.tile_start_level - game.config.attack_damage * 0.6 * 0.2


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_cannot_defend_empty():
    """Test that a player cannot defend an empty tile in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    await aplay_turn(game, grid := get_grid(game))
    await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(0, 1), ActionType.DEFEND, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.DEFEND_EMPTY)
    assert (await game.occupiedtile_set.filter(col=0, row=1).afirst()) is None


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_cannot_defend_other():
    """Test that a player cannot defend a tile of another player in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    await make_player_in_game(game, await make_player(2), [Tile(0, 1)])
    await aplay_turn(game, grid := get_grid(game))
    await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(0, 1), ActionType.DEFEND, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.DEFEND_OTHER)
    assert (await game.occupiedtile_set.aget(col=0, row=1)).level == game.config.tile_start_level


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_can_defend_self_tile():
    """Test that a player can defend a tile of its own in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    await aplay_turn(game, grid := get_grid(game))
    await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(0, 0), ActionType.DEFEND, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.SUCCESS)
    assert (
        await game.occupiedtile_set.aget(col=0, row=0)
    ).level == game.config.tile_start_level + game.config.defend_improvement * 0.6


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_cannot_grow_occupied():
    """Test that a player cannot grow an occupied tile in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(0, 1)])
    await aplay_turn(game, grid := get_grid(game))

    for _ in range(game.config.respawn_protected_max_turns + 1):
        await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(0, 1), ActionType.GROW, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_OCCUPIED)
    assert (await game.occupiedtile_set.aget(col=0, row=1)).player_in_game_id == player_in_game2.id


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_can_grow_empty():
    """Test that a player can grow an empty tile in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    await aplay_turn(game, grid := get_grid(game))
    await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, Tile(0, 1), ActionType.GROW, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.SUCCESS)
    assert (await game.occupiedtile_set.aget(col=0, row=1)).level == game.config.tile_start_level * 0.6


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_turn_mode_can_bank():
    """Test that a player can bank in turn mode."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    await aplay_turn(game, grid := get_grid(game))
    await game.anext_turn()

    assert (action := await asave_action(player_in_game.player, game, None, ActionType.BANK, 0.6)) is not None
    await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.SUCCESS)
    await player_in_game.arefresh_from_db()
    assert player_in_game.banked_actions == game.config.bank_value * 0.6


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_welcome_chat_message_if_protected():
    """Test that a welcome chat message is sent if the first grow is on a protected tile."""
    game, _, _ = await make_game_and_player(Tile(0, 0))
    await aplay_turn(game, get_grid(game))
    await game.anext_turn()

    player_in_game2 = await make_player_in_game(game, (player2 := await make_player(2)))

    # message should be sent the first time, with a chat message
    assert (action := await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.GROW)) is not None
    messages = await aplay_turn(game, grid := get_grid(game))
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_PROTECTED)
    assert len(messages) == 1
    assert messages[0].player_id == player_in_game2.player_id
    assert messages[0].kind == GameMessageKind.SPAWN_FAILED
    assert messages[0].chat_text is not None
    await player2.arefresh_from_db()
    assert player2.welcome_chat_message_sent_at is None

    await game.anext_turn()

    # and next time too
    assert (action := await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.GROW)) is not None
    messages = await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_PROTECTED)
    assert len(messages) == 1
    assert messages[0].player_id == player_in_game2.player_id
    assert messages[0].kind == GameMessageKind.SPAWN_FAILED
    assert messages[0].chat_text is not None
    await player2.arefresh_from_db()
    assert player2.welcome_chat_message_sent_at is None

    await game.anext_turn()

    # but if a real welcome chat message was sent, no new one should be sent
    player2.welcome_chat_message_sent_at = timezone.now()
    await player2.asave()

    assert (action := await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.GROW)) is not None
    messages = await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_PROTECTED)
    assert len(messages) == 1
    assert messages[0].player_id == player_in_game2.player_id
    assert messages[0].kind == GameMessageKind.SPAWN_FAILED
    assert messages[0].chat_text is None


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_welcome_chat_message_if_protected_then_free():
    """Test that two (sadly) welcome chat messages are sent if the first grow is on a protected tile but not the 2nd."""
    game, _, _ = await make_game_and_player(Tile(0, 0))
    await aplay_turn(game, get_grid(game))
    await game.anext_turn()

    player_in_game2 = await make_player_in_game(game, (player2 := await make_player(2)), level=2)

    assert (action1 := await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.GROW)) is not None
    assert (action2 := await asave_action(player_in_game2.player, game, Tile(0, 1), ActionType.GROW)) is not None
    messages = await aplay_turn(game, get_grid(game))
    await assert_action_state(action1, ActionState.FAILURE, ActionFailureReason.GROW_PROTECTED)
    await assert_action_state(action2, ActionState.SUCCESS)
    assert len(messages) == 2
    assert messages[0].player_id == player_in_game2.player_id
    assert messages[0].kind == GameMessageKind.SPAWN_FAILED
    assert messages[0].chat_text is not None
    assert messages[1].player_id == player_in_game2.player_id
    assert messages[1].kind == GameMessageKind.SPAWN
    assert messages[1].chat_text is not None
    await player2.arefresh_from_db()
    assert player2.welcome_chat_message_sent_at is not None


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_welcome_chat_message_if_occupied_in_turn_mode():
    """Test that a welcome chat message is sent if the first grow is on an occupied tile in turn mode."""
    game, _, _ = await make_turn_game_and_player(Tile(0, 0))
    await aplay_turn(game, get_grid(game))
    await game.anext_turn()

    player_in_game2 = await make_player_in_game(game, (player2 := await make_player(2)))

    # message should be sent the first time, with a chat message
    assert (action := await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.GROW)) is not None
    messages = await aplay_turn(game, grid := get_grid(game))
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_OCCUPIED)
    assert len(messages) == 1
    assert messages[0].player_id == player_in_game2.player_id
    assert messages[0].kind == GameMessageKind.SPAWN_FAILED
    assert messages[0].chat_text is not None
    await player2.arefresh_from_db()
    assert player2.welcome_chat_message_sent_at is None

    await game.anext_turn()

    # and next time too
    assert (action := await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.GROW)) is not None
    messages = await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_OCCUPIED)
    assert len(messages) == 1
    assert messages[0].player_id == player_in_game2.player_id
    assert messages[0].kind == GameMessageKind.SPAWN_FAILED
    assert messages[0].chat_text is not None
    await player2.arefresh_from_db()
    assert player2.welcome_chat_message_sent_at is None

    await game.anext_turn()

    # but if a real welcome chat message was sent, no new one should be sent
    player2.welcome_chat_message_sent_at = timezone.now()
    await player2.asave()

    assert (action := await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.GROW)) is not None
    messages = await aplay_turn(game, grid)
    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_OCCUPIED)
    assert len(messages) == 1
    assert messages[0].player_id == player_in_game2.player_id
    assert messages[0].kind == GameMessageKind.SPAWN_FAILED
    assert messages[0].chat_text is None


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_welcome_chat_message_is_not_sent_twice():
    """Test that a welcome chat message is not sent twice."""
    game, _, _ = await make_game_and_player(Tile(0, 0))
    await aplay_turn(game, get_grid(game))
    await game.anext_turn()

    player_in_game2 = await make_player_in_game(game, (player2 := await make_player(2)), level=2)

    # message should be sent the first time, with a chat message
    assert (action1 := await asave_action(player_in_game2.player, game, Tile(0, 1), ActionType.GROW)) is not None
    assert (action2 := await asave_action(player_in_game2.player, game, Tile(1, 0), ActionType.GROW)) is not None
    messages = await aplay_turn(game, get_grid(game))
    await assert_action_state(action1, ActionState.SUCCESS)
    await assert_action_state(action2, ActionState.SUCCESS)
    assert len(messages) == 1
    assert messages[0].player_id == player_in_game2.player_id
    assert messages[0].kind == GameMessageKind.SPAWN
    assert messages[0].chat_text is not None
    await player2.arefresh_from_db()
    assert player2.welcome_chat_message_sent_at is not None

    await game.anext_turn()

    # but not the second time
    assert (action := await asave_action(player_in_game2.player, game, Tile(1, 1), ActionType.GROW)) is not None
    messages = await aplay_turn(game, get_grid(game))
    await assert_action_state(action, ActionState.SUCCESS)
    assert len(messages) == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_first_action_must_be_grow():
    """Test that the first action must be "grow"."""
    game, _, player_in_game = await make_turn_game_and_player(Tile(0, 0))
    await aplay_turn(game, get_grid(game))
    await game.anext_turn()

    # should work whether we have a fresh PlayerInGame object
    player_in_game2 = await make_player_in_game(game, await make_player(2))
    assert (await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.ATTACK)) is None
    assert (await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.DEFEND)) is None
    assert (await asave_action(player_in_game2.player, game, None, ActionType.BANK)) is None

    # or a dead one
    player_in_game3 = await make_player_in_game(game, await make_player(3), [Tile(0, 1)])
    await player_in_game3.adie(game.current_turn, player_in_game)

    for _ in range(game.config.respawn_cooldown_turns + 1):
        await game.anext_turn()

    assert (await asave_action(player_in_game3.player, game, Tile(0, 0), ActionType.ATTACK)) is None
    assert (await asave_action(player_in_game3.player, game, Tile(0, 0), ActionType.DEFEND)) is None
    assert (await asave_action(player_in_game3.player, game, None, ActionType.BANK)) is None

    # or no PlayerInGame object at all
    player4 = await make_player(4)
    assert (await asave_action(player4, game, Tile(0, 0), ActionType.ATTACK)) is None
    assert (await asave_action(player4, game, Tile(0, 0), ActionType.DEFEND)) is None
    assert (await asave_action(player4, game, None, ActionType.BANK)) is None


async def create_game_loop(
    game: Optional[Game] = None,
    waiting_for_players_duration: Optional[timedelta] = None,
    collecting_actions_duration: Optional[timedelta] = None,
) -> GameLoop:
    """Create a game loop and start it."""
    clicks_queue: ClicksQueue = asyncio.Queue()
    chat_messages_queue: ChatMessagesQueue = asyncio.Queue()
    game_messages_queue: GameMessagesQueue = asyncio.Queue()
    clicks_allowed_event = asyncio.Event()

    if game is None:
        game = await make_game()
    grid = get_grid(game)

    return GameLoop(
        clicks_queue,
        clicks_allowed_event,
        game,
        grid,
        chat_messages_queue,
        game_messages_queue,
        waiting_for_players_duration=waiting_for_players_duration,
        collecting_actions_duration=collecting_actions_duration,
        latency_delay=timedelta(seconds=0),
        go_next_turn_if_no_actions=True,
    )


async def start_game_loop(game_loop: GameLoop) -> asyncio.Task[None]:
    """Start a game loop."""
    return asyncio.create_task(game_loop.run(), name="game_loop")


async def end_game_loop(game_loop: GameLoop, game_task: asyncio.Task[None]):
    """End a game loop."""
    await game_loop.end()
    await game_task


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_game_loop():
    """Test the game loop."""
    game_loop = await create_game_loop(collecting_actions_duration=timedelta(seconds=0.01))
    game_task = await start_game_loop(game_loop)
    await asyncio.sleep(0.1)
    await end_game_loop(game_loop, game_task)
    assert game_loop.game.current_turn > 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_game_loop_step_collecting_actions():
    """Test the game loop step "collecting actions"."""
    game_loop = await create_game_loop(collecting_actions_duration=timedelta(seconds=5))
    game_loop.game.current_turn_step = GameStep.COLLECTING_ACTIONS
    await game_loop.game.asave()

    player1 = await make_player(1)
    player2 = await make_player(2)
    await game_loop.clicks_queue.put(PlayerClick(player1, ClickTarget.MAP, Tile(0, 0)))
    await game_loop.clicks_queue.put(PlayerClick(player2, ClickTarget.MAP, Tile(2, 2)))

    start_time = time()
    step_task = asyncio.create_task(game_loop.run_current_step())
    await asyncio.sleep(0.1)
    game_loop.end_step_event.set()
    await step_task
    assert time() - start_time < 2  # to ensure that the loop ended before the timeout, thanks to end_step_event

    player_in_game1 = await PlayerInGame.objects.filter(player=player1, game=game_loop.game).afirst()
    assert player_in_game1 is not None
    actions = await sync_to_async(lambda: list(Action.objects.filter(player_in_game=player_in_game1).all()))()
    assert len(actions) == 1
    action1 = actions[0]
    assert action1.action_type == ActionType.GROW
    assert action1.tile == Tile(0, 0)
    assert action1.state == ActionState.CONFIRMED

    player_in_game2 = await PlayerInGame.objects.filter(player=player2, game=game_loop.game).afirst()
    assert player_in_game2 is not None
    actions = await sync_to_async(lambda: list(Action.objects.filter(player_in_game=player_in_game2).all()))()
    assert len(actions) == 1
    action2 = actions[0]
    assert action2.action_type == ActionType.GROW
    assert action2.tile == Tile(2, 2)
    assert action2.state == ActionState.CONFIRMED

    assert action2.confirmed_at > action1.confirmed_at


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_game_loop_step_executing_actions():
    """Test the game loop step "executing actions"."""
    game_loop = await create_game_loop(collecting_actions_duration=timedelta(seconds=0.01))

    player = await make_player()
    await game_loop.clicks_queue.put(PlayerClick(player, ClickTarget.MAP, Tile(0, 0)))

    game_loop.game.current_turn_step = GameStep.COLLECTING_ACTIONS
    await game_loop.game.asave()
    await game_loop.run_current_step()

    game_loop.game.current_turn_step = GameStep.EXECUTING_ACTIONS
    await game_loop.game.asave()
    await game_loop.run_current_step()

    player_in_game = await PlayerInGame.objects.filter(player=player, game=game_loop.game).afirst()
    assert player_in_game is not None
    await assert_has_tiles(player_in_game, [Tile(0, 0)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_game_loop_next_step():
    """Test the game loop next step."""
    game_loop = await create_game_loop(collecting_actions_duration=timedelta(seconds=0.01))
    assert game_loop.game.current_turn_step == GameStep.WAITING_FOR_PLAYERS
    assert game_loop.game.current_turn == 0
    await game_loop.game.anext_step()
    assert game_loop.game.current_turn_step == GameStep.COLLECTING_ACTIONS
    assert game_loop.game.current_turn == 0
    await game_loop.game.anext_step()
    assert game_loop.game.current_turn_step == GameStep.RANDOM_EVENTS_BEFORE
    assert game_loop.game.current_turn == 0
    await game_loop.game.anext_step()
    assert game_loop.game.current_turn_step == GameStep.EXECUTING_ACTIONS
    assert game_loop.game.current_turn == 0
    await game_loop.game.anext_step()
    assert game_loop.game.current_turn_step == GameStep.RANDOM_EVENTS_AFTER
    assert game_loop.game.current_turn == 0
    await game_loop.game.anext_step()
    assert game_loop.game.current_turn_step == GameStep.WAITING_FOR_PLAYERS
    assert game_loop.game.current_turn == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_only_new_player_can_click_on_waiting_for_players_step():  # pylint: disable=too-many-statements
    """Test that only new players can click on the "waiting for players" step."""
    game = await make_game(mode=GameMode.TURN_BY_TURN)
    game_loop = await create_game_loop(game=game, waiting_for_players_duration=timedelta(seconds=0.5))
    game_loop.game.current_turn_step = GameStep.WAITING_FOR_PLAYERS
    await game_loop.game.asave()

    player1 = await make_player(1)
    player2 = await make_player(2)
    player3 = await make_player(3)
    await game_loop.clicks_queue.put(PlayerClick(player1, ClickTarget.MAP, Tile(0, 0)))
    await game_loop.clicks_queue.put(PlayerClick(player2, ClickTarget.MAP, Tile(2, 2)))
    await game_loop.clicks_queue.put(PlayerClick(player3, ClickTarget.MAP, Tile(2, 2)))

    await game_loop.run_current_step()

    player_in_game1 = await PlayerInGame.objects.filter(player=player1, game=game_loop.game).afirst()
    assert player_in_game1 is not None
    actions = await sync_to_async(lambda: list(Action.objects.filter(player_in_game=player_in_game1).all()))()
    assert len(actions) == 1
    action = actions[0]
    assert action.action_type == ActionType.GROW
    assert action.tile == Tile(0, 0)
    assert action.state == ActionState.SUCCESS

    player_in_game2 = await PlayerInGame.objects.filter(player=player2, game=game_loop.game).afirst()
    assert player_in_game2 is not None
    actions = await sync_to_async(lambda: list(Action.objects.filter(player_in_game=player_in_game2).all()))()
    assert len(actions) == 1
    action = actions[0]
    assert action.action_type == ActionType.GROW
    assert action.tile == Tile(2, 2)
    assert action.state == ActionState.SUCCESS

    player_in_game3 = await PlayerInGame.objects.filter(player=player3, game=game_loop.game).afirst()
    assert player_in_game3 is not None
    actions = await sync_to_async(lambda: list(Action.objects.filter(player_in_game=player_in_game3).all()))()
    assert len(actions) == 1
    action3 = actions[0]
    assert action3.action_type == ActionType.GROW
    assert action3.tile == Tile(2, 2)
    await assert_action_state(action3, ActionState.FAILURE, ActionFailureReason.GROW_OCCUPIED)

    # next turn, only player3 would be able to join
    await game.anext_turn()
    game_loop.game.current_turn_step = GameStep.WAITING_FOR_PLAYERS
    await game_loop.game.asave()

    await game_loop.clicks_queue.put(PlayerClick(player1, ClickTarget.MAP, Tile(0, 1)))
    await game_loop.clicks_queue.put(PlayerClick(player2, ClickTarget.MAP, Tile(1, 2)))
    await game_loop.clicks_queue.put(PlayerClick(player3, ClickTarget.MAP, Tile(2, 1)))

    await game_loop.run_current_step()

    assert await PlayerInGame.objects.filter(player=player1, game=game_loop.game).acount() == 1
    actions = await sync_to_async(lambda: list(Action.objects.filter(player_in_game=player_in_game1).all()))()
    assert len(actions) == 1  # no new actions, as expected

    assert await PlayerInGame.objects.filter(player=player2, game=game_loop.game).acount() == 1
    actions = await sync_to_async(lambda: list(Action.objects.filter(player_in_game=player_in_game2).all()))()
    assert len(actions) == 1  # no new actions, as expected

    assert await PlayerInGame.objects.filter(player=player3, game=game_loop.game).acount() == 2
    player_in_game3 = await PlayerInGame.objects.filter(player=player3, game=game_loop.game).alast()
    assert player_in_game3 is not None
    actions = await sync_to_async(lambda: list(Action.objects.filter(player_in_game=player_in_game3).all()))()
    assert len(actions) == 1
    action = actions[0]
    assert action.action_type == ActionType.GROW
    assert action.tile == Tile(2, 1)
    assert action.state == ActionState.SUCCESS
    assert player_in_game3.first_in_game_for_player is True


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_actions_efficiency_during_a_turn():
    """Test that actions are executed in the correct order."""
    game_loop = await create_game_loop()

    player_in_game = await make_player_in_game(game=game_loop.game, player=await make_player(1), level=5)
    tiles_and_delay = [(Tile(0, 0), 0), (Tile(1, 0), 1), (Tile(0, 1), 3), (Tile(1, 1), 6), (Tile(2, 0), 10)]
    start_time = timezone.now()
    for tile, delay in tiles_and_delay:
        await Action.objects.acreate(
            player_in_game=player_in_game,
            game=game_loop.game,
            turn=game_loop.game.current_turn,
            action_type=ActionType.GROW,
            tile_col=tile.col,
            tile_row=tile.row,
            state=ActionState.CONFIRMED,
            confirmed_at=start_time + timedelta(seconds=delay),
        )
    await sync_to_async(game_loop.step_collecting_actions_compute_efficiency)(game_loop.game)
    actions = await sync_to_async(
        lambda: list(game_loop.game.confirmed_actions_for_turn(game_loop.game.current_turn).order_by("confirmed_at"))
    )()
    assert actions[0].efficiency == 1.0
    assert actions[1].efficiency == 0.95
    assert actions[2].efficiency == 0.85
    assert actions[3].efficiency == 0.7
    assert actions[4].efficiency == 0.5


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_compute_player_level():
    """Test that player level is computed correctly."""
    game = await make_turn_game()
    player_in_game = await make_player_in_game(
        game, await make_player(), [Tile(0, 1), Tile(1, 0), Tile(1, 1), Tile(1, 2), Tile(2, 1)], 1
    )
    assert await player_in_game.compute_level(1, {}) == 1
    assert await player_in_game.compute_level(2, {}) == 2
    assert await player_in_game.compute_level(1, {2: 2, 4: 3, 8: 4}) == 3
    assert await player_in_game.compute_level(2, {20: 5, 40: 10, 50: 100}) == 2
