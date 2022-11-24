"""Tests for the grid package."""

from datetime import timedelta
from typing import Optional, Sequence, Set, cast

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone
from freezegun import freeze_time

from hexpo_game.core.constants import (
    RESPAWN_FORBID_DURATION,
    RESPAWN_PROTECTED_DURATION,
    ActionFailureReason,
    ActionState,
    ActionType,
    GameMode,
)
from hexpo_game.core.game import aplay_turn, asave_action
from hexpo_game.core.grid import Grid
from hexpo_game.core.models import Action, Game, OccupiedTile, Player, PlayerInGame
from hexpo_game.core.types import Color, Tile


async def make_game(mode: GameMode = GameMode.FREE_NEIGHBOR) -> Game:
    """Create a game in the given mode."""
    nb_cols, nb_rows = Grid.compute_grid_size(20, 1 / 2)
    return await Game.objects.acreate(
        mode=mode,
        grid_nb_cols=nb_cols,
        grid_nb_rows=nb_rows,
        max_players_allowed=20,
        current_turn_end=timezone.now() + timedelta(minutes=10),
    )


async def make_player(external_id: int = 1, name: str = "Player") -> Player:
    """Create a player."""
    return await Player.objects.acreate(external_id=external_id, name=name)


async def make_player_in_game(
    game: Game, player: Player, occupied_tiles: Optional[Sequence[Tile]] = None
) -> PlayerInGame:
    """Create a player in game."""
    player_in_game = await PlayerInGame.objects.acreate(
        game=game,
        player=player,
        started_turn=0,
        start_tile_col=0,
        start_tile_row=0,
        color=Color(0, 0, 0).as_hex,
    )
    for tile in occupied_tiles or []:
        # pylint: disable=duplicate-code
        await OccupiedTile.objects.aupdate_or_create(
            game=game,
            col=tile.col,
            row=tile.row,
            defaults=dict(  # noqa: C408
                player_in_game=player_in_game,
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
    first_tile: Tile, game_mode: GameMode = GameMode.FREE_NEIGHBOR
) -> tuple[Game, Player, PlayerInGame]:
    """Make a game and a player in it."""
    game = await make_game(mode=game_mode)
    player = await make_player()
    player_in_game = await make_player_in_game(game, player, [first_tile])
    return game, player, player_in_game


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

    await aplay_turn(game, get_grid(game), 0)

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

    assert (action := await asave_action(player, game, Tile(0, 0))) is not None

    assert action.player_in_game_id == player_in_game.id

    await aplay_turn(game, get_grid(game), 0)

    await assert_action_state(action, ActionState.SUCCESS)
    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(0, 1)])
    await assert_has_tiles(player_in_game, [Tile(0, 0), Tile(0, 1)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_non_neighbor_tile_in_free_neighbor_mode():
    """Test that a player cannot click on an invalid tile in FREE_NEIGHBOR mode."""
    game, player, player_in_game = await make_game_and_player(Tile(1, 1))

    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game), 0)

    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_NO_NEIGHBOR)
    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(1, 1)])
    await assert_has_tiles(player_in_game, [Tile(1, 1)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_non_neighbor_tile_in_free_full_mode():
    """Test that a player cannot click on an invalid tile in FREE_FULL mode."""
    game, player, player_in_game = await make_game_and_player(Tile(1, 1), game_mode=GameMode.FREE_FULL)

    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game), 0)

    await assert_action_state(action, ActionState.SUCCESS)
    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(1, 1)])
    await assert_has_tiles(player_in_game, [Tile(0, 0), Tile(1, 1)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_self_occupied_tile():
    """Test that a player cannot click on a tile occupied by themselves."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 0))

    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game), 0)

    await assert_action_state(action, ActionState.FAILURE, ActionFailureReason.GROW_SELF)
    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(0, 0)])
    await assert_has_tiles(player_in_game, [Tile(0, 0)])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_protected_tile():
    """Test that a player cannot click on a protected tile."""
    game, player, player_in_game = await make_game_and_player(Tile(0, 0))
    player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(0, 1)])

    assert (action := await asave_action(player, game, Tile(0, 1))) is not None
    await aplay_turn(game, get_grid(game), 0)

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
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 2):
        game, player, player_in_game = await make_game_and_player(Tile(0, 1))
        player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(0, 0), Tile(1, 0)])

    await assert_has_actions(player_in_game, [Tile(0, 1)])
    await assert_has_tiles(player_in_game, [Tile(0, 1)])
    await assert_has_actions(player_in_game2, [Tile(0, 0), Tile(1, 0)])
    await assert_has_tiles(player_in_game2, [Tile(0, 0), Tile(1, 0)])

    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game), 0)

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
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 2):
        game, player, player_in_game = await make_game_and_player(Tile(0, 1))
        player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(0, 0)])

    assert (action := await asave_action(player, game, Tile(0, 0))) is not None
    await aplay_turn(game, get_grid(game), 0)

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
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 2):
        game, player, player_in_game = await make_game_and_player(Tile(0, 0))
        player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(1, 0)])

    await asave_action(player_in_game2.player, game, Tile(0, 0))
    await aplay_turn(game, get_grid(game), 0)
    await assert_death(player_in_game, True, player_in_game2.id)

    assert await asave_action(player, game, Tile(0, 1)) is None
    await aplay_turn(game, get_grid(game), 0)

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
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 4):
        game, player, player_in_game = await make_game_and_player(Tile(0, 0))
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 2):
        player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(1, 0)])

    await asave_action(player_in_game2.player, game, Tile(0, 0))
    await aplay_turn(game, get_grid(game), 0)
    await assert_death(player_in_game, True, player_in_game2.id)

    player_in_game.dead_at = timezone.now() - RESPAWN_FORBID_DURATION * 2
    await player_in_game.asave()

    assert (action := await asave_action(player, game, Tile(0, 1))) is not None
    await aplay_turn(game, get_grid(game), 0)

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
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 4):
        game, player, player_in_game = await make_game_and_player(Tile(0, 0))
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 2):
        player_in_game2 = await make_player_in_game(game, await make_player(2), [Tile(1, 0)])

    assert (action_1 := await asave_action(player, game, Tile(0, 1))) is not None
    assert (action_2 := await asave_action(player_in_game2.player, game, Tile(0, 0))) is not None
    assert (action_3 := await asave_action(player_in_game2.player, game, Tile(0, 1))) is not None
    assert (action_4 := await asave_action(player, game, Tile(1, 1))) is not None

    await aplay_turn(game, get_grid(game), 0)

    await assert_action_state(action_1, ActionState.SUCCESS)
    await assert_action_state(action_2, ActionState.SUCCESS)
    await assert_action_state(action_3, ActionState.SUCCESS)
    await assert_action_state(action_4, ActionState.FAILURE, ActionFailureReason.DEAD)

    await assert_has_actions(player_in_game, [Tile(0, 0), Tile(0, 1), Tile(1, 1)])
    await assert_has_tiles(player_in_game, [])
    await assert_death(player_in_game, True, player_in_game2.id)

    await assert_has_actions(player_in_game2, [Tile(1, 0), Tile(0, 0), Tile(0, 1)])
    await assert_has_tiles(player_in_game2, [Tile(1, 0), Tile(0, 0), Tile(0, 1)])
