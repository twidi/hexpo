"""Tests for the grid package."""

from datetime import timedelta
from typing import Optional, Sequence

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone
from freezegun import freeze_time

from hexpo_game.core.constants import (
    RESPAWN_FORBID_DURATION,
    RESPAWN_PROTECTED_DURATION,
    ActionState,
    ActionType,
    GameMode,
)
from hexpo_game.core.game import on_maybe_tile_click
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
            state=ActionState.SUCCESSFUL,
        )

    return player_in_game


def get_grid(game: Game) -> Grid:
    """Get the grid of the game."""
    return Grid(game.grid_nb_cols, game.grid_nb_rows)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_new_player():
    """Test that a new player can click on a tile."""
    game = await make_game()
    player = await make_player()
    assert await game.playeringame_set.acount() == 0
    assert await game.occupiedtile_set.acount() == 0
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 0))
    assert returned_player_in_game.player_id == player.id
    assert await returned_player_in_game.action_set.filter(tile_col=0, tile_row=0).acount() == 1
    assert await returned_player_in_game.occupiedtile_set.filter(col=0, row=0).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_no_tile():
    """Test that a player cannot click on a tile if there is no tile."""
    game = await make_game()
    player = await make_player()
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), None)
    assert returned_player_in_game is None
    assert await game.playeringame_set.acount() == 0
    assert await game.occupiedtile_set.acount() == 0
    assert await Action.objects.filter(game=game).acount() == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_free_tile():
    """Test that an existing player can click on a free tile."""
    game = await make_game()
    player = await make_player()
    player_in_game = await make_player_in_game(game, player, [Tile(0, 1)])
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 1
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 0))
    assert returned_player_in_game == player_in_game
    assert await player_in_game.action_set.acount() == 2
    assert await player_in_game.action_set.filter(tile_col=0, tile_row=0).acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 2
    assert await player_in_game.occupiedtile_set.filter(col=0, row=0).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_non_neighbor_tile_in_free_neighbor_mode():
    """Test that a player cannot click on an invalid tile in FREE_NEIGHBOR mode."""
    game = await make_game()
    player = await make_player()
    player_in_game = await make_player_in_game(game, player, [Tile(1, 1)])
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 1
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 0))
    assert returned_player_in_game == player_in_game
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.action_set.filter(tile_col=0, tile_row=0).acount() == 0
    assert await player_in_game.occupiedtile_set.acount() == 1
    assert await player_in_game.occupiedtile_set.filter(col=0, row=0).acount() == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_non_neighbor_tile_in_free_full_mode():
    """Test that a player cannot click on an invalid tile in FREE_FULL mode."""
    game = await make_game()
    game.mode = GameMode.FREE_FULL
    await sync_to_async(game.save)()
    player = await make_player()
    player_in_game = await make_player_in_game(game, player, [Tile(1, 1)])
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 1
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 0))
    assert returned_player_in_game == player_in_game
    assert await player_in_game.action_set.acount() == 2
    assert await player_in_game.action_set.filter(tile_col=0, tile_row=0).acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 2
    assert await player_in_game.occupiedtile_set.filter(col=0, row=0).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_self_occupied_tile():
    """Test that a player cannot click on a tile occupied by themselves."""
    game = await make_game()
    player = await make_player()
    player_in_game = await make_player_in_game(game, player, [Tile(0, 0)])
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 1
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 0))
    assert returned_player_in_game == player_in_game
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.action_set.filter(tile_col=0, tile_row=0).acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 1
    assert await player_in_game.occupiedtile_set.filter(col=0, row=0).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_protected_tile():
    """Test that a player cannot click on a protected tile."""
    game = await make_game()
    player = await make_player()
    player_in_game = await make_player_in_game(game, player, [Tile(0, 0)])
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 1
    player2 = await make_player(2)
    player_in_game2 = await make_player_in_game(game, player2, [Tile(0, 1)])
    assert await player_in_game2.action_set.acount() == 1
    assert await player_in_game2.occupiedtile_set.acount() == 1
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 0))
    assert returned_player_in_game == player_in_game
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.action_set.filter(tile_col=0, tile_row=0).acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 1
    assert await player_in_game.occupiedtile_set.filter(col=0, row=0).acount() == 1
    await sync_to_async(player_in_game.refresh_from_db)()
    assert player_in_game.dead_at is None
    assert player_in_game.killed_by is None
    assert await player_in_game2.action_set.acount() == 1
    assert await player_in_game2.action_set.filter(tile_col=0, tile_row=1).acount() == 1
    assert await player_in_game2.occupiedtile_set.acount() == 1
    assert await player_in_game2.occupiedtile_set.filter(col=0, row=1).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_tile_occupied_by_other():
    """Test that a player can click on a tile (among others) occupied by another player."""
    game = await make_game()
    player = await make_player()
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 2):
        player_in_game = await make_player_in_game(game, player, [Tile(0, 1)])
        player2 = await make_player(2)
        player_in_game2 = await make_player_in_game(game, player2, [Tile(0, 0), Tile(1, 1)])
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 1
    assert await player_in_game2.action_set.acount() == 2
    assert await player_in_game2.occupiedtile_set.acount() == 2
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 0))
    assert returned_player_in_game == player_in_game
    assert await player_in_game.action_set.acount() == 2
    assert await player_in_game.action_set.filter(tile_col=0, tile_row=0).acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 2
    assert await player_in_game.occupiedtile_set.filter(col=0, row=0).acount() == 1
    assert await player_in_game2.action_set.acount() == 2
    assert await player_in_game2.action_set.filter(tile_col=0, tile_row=0).acount() == 1
    assert await player_in_game2.occupiedtile_set.acount() == 1
    assert await player_in_game2.occupiedtile_set.filter(col=0, row=0).acount() == 0
    assert await player_in_game2.occupiedtile_set.filter(col=1, row=1).acount() == 1
    await sync_to_async(player_in_game2.refresh_from_db)()
    assert player_in_game2.dead_at is None
    assert player_in_game2.killed_by is None
    assert await PlayerInGame.objects.filter(player=player2).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_tile_last_occupied_by_other():
    """Test that a player can click on the last tile occupied by another player."""
    game = await make_game()
    player = await make_player()
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 2):
        player_in_game = await make_player_in_game(game, player, [Tile(0, 1)])
        player2 = await make_player(2)
        player_in_game2 = await make_player_in_game(game, player2, [Tile(0, 0)])
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 1
    assert await player_in_game2.action_set.acount() == 1
    assert await player_in_game2.occupiedtile_set.acount() == 1
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 0))
    assert returned_player_in_game == player_in_game
    assert await player_in_game.action_set.acount() == 2
    assert await player_in_game.action_set.filter(tile_col=0, tile_row=0).acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 2
    assert await player_in_game.occupiedtile_set.filter(col=0, row=0).acount() == 1
    assert await player_in_game2.action_set.acount() == 1
    assert await player_in_game2.action_set.filter(tile_col=0, tile_row=0).acount() == 1
    assert await player_in_game2.occupiedtile_set.acount() == 0
    assert await player_in_game2.occupiedtile_set.filter(col=0, row=0).acount() == 0
    await sync_to_async(player_in_game2.refresh_from_db)()
    assert player_in_game2.dead_at is not None
    assert player_in_game2.killed_by_id == player_in_game.id
    assert await PlayerInGame.objects.filter(player=player2).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_tile_after_recent_death():
    """Test that a player cannot click on a tile if recently dead."""
    game = await make_game()
    player = await make_player()
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 2):
        player_in_game = await make_player_in_game(game, player, [Tile(0, 0)])
        player2 = await make_player(2)
        player_in_game2 = await make_player_in_game(game, player2, [Tile(1, 0)])
    await sync_to_async(on_maybe_tile_click)(player2, game, get_grid(game), Tile(0, 0))
    await sync_to_async(player_in_game.refresh_from_db)()
    assert player_in_game.dead_at is not None
    assert player_in_game.killed_by_id == player_in_game2.id
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 0
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 1))
    assert returned_player_in_game == player_in_game
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 0
    await sync_to_async(player_in_game.refresh_from_db)()
    assert player_in_game.dead_at is not None
    assert player_in_game.killed_by_id == player_in_game2.id
    assert await PlayerInGame.objects.filter(player=player).acount() == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_on_click_tile_after_not_recent_death():
    """Test that a player can click on a tile if dead but not recently."""
    game = await make_game()
    player = await make_player()
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 4):
        player_in_game = await make_player_in_game(game, player, [Tile(0, 0)])
    player2 = await make_player(2)
    with freeze_time(timezone.now() - RESPAWN_PROTECTED_DURATION * 2):
        await make_player_in_game(game, player2, [Tile(1, 0)])
        player_in_game2 = await sync_to_async(on_maybe_tile_click)(player2, game, get_grid(game), Tile(0, 0))
    await sync_to_async(player_in_game.refresh_from_db)()
    assert player_in_game.dead_at is not None
    assert player_in_game.killed_by_id == player_in_game2.id
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 0
    player_in_game.dead_at = timezone.now() - RESPAWN_FORBID_DURATION * 2
    await sync_to_async(player_in_game.save)()
    returned_player_in_game = await sync_to_async(on_maybe_tile_click)(player, game, get_grid(game), Tile(0, 1))
    assert returned_player_in_game != player_in_game
    assert returned_player_in_game.player_id == player.id
    assert await player_in_game.action_set.acount() == 1
    assert await player_in_game.occupiedtile_set.acount() == 0
    assert await returned_player_in_game.action_set.acount() == 1
    assert await returned_player_in_game.occupiedtile_set.acount() == 1
    await sync_to_async(player_in_game.refresh_from_db)()
    assert player_in_game.dead_at is not None
    assert player_in_game.killed_by_id == player_in_game2.id
    await sync_to_async(returned_player_in_game.refresh_from_db)()
    assert returned_player_in_game.dead_at is None
    assert returned_player_in_game.killed_by is None
    assert await PlayerInGame.objects.filter(player=player).acount() == 2
