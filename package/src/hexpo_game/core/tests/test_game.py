"""Tests for the grid package."""

from datetime import timedelta
from typing import Optional, Sequence, Set, cast

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from hexpo_game.core.constants import (
    ActionFailureReason,
    ActionState,
    ActionType,
    GameMode,
)
from hexpo_game.core.game import aplay_turn, asave_action
from hexpo_game.core.grid import Grid
from hexpo_game.core.models import Action, Game, OccupiedTile, Player, PlayerInGame
from hexpo_game.core.types import Color, GameMessageKind, Tile


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
    first_tile: Tile, game_mode: GameMode = GameMode.FREE_NEIGHBOR, player_level: int = 1
) -> tuple[Game, Player, PlayerInGame]:
    """Make a game and a player in it."""
    game = await make_game(mode=game_mode)
    player = await make_player()
    player_in_game = await make_player_in_game(game, player, [first_tile], player_level)
    return game, player, player_in_game


async def make_turn_game_and_player(first_tile: Tile, player_level: int = 1) -> tuple[Game, Player, PlayerInGame]:
    """Make a turn game and a player in it."""
    return await make_game_and_player(first_tile, GameMode.TURN_BY_TURN, player_level)


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
    """Test that a welcome chat message is sent if the first grow is on a protected tile but not the second."""
    game, _, _ = await make_game_and_player(Tile(0, 0))
    await aplay_turn(game, get_grid(game))
    await game.anext_turn()

    player_in_game2 = await make_player_in_game(game, (player2 := await make_player(2)), level=2)

    assert (action1 := await asave_action(player_in_game2.player, game, Tile(0, 0), ActionType.GROW)) is not None
    assert (action2 := await asave_action(player_in_game2.player, game, Tile(0, 1), ActionType.GROW)) is not None
    messages = await aplay_turn(game, get_grid(game))
    await assert_action_state(action1, ActionState.FAILURE, ActionFailureReason.GROW_PROTECTED)
    await assert_action_state(action2, ActionState.SUCCESS)
    assert len(messages) == 1
    assert messages[0].player_id == player_in_game2.player_id
    assert messages[0].kind == GameMessageKind.SPAWN
    assert messages[0].chat_text is not None
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
