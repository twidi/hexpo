"""Main game loop and functions."""

import logging
from typing import Optional

from asgiref.sync import sync_to_async
from django.utils import timezone

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .click_handler import COORDINATES, get_click_target
from .constants import (
    NB_COLORS,
    PALETTE,
    RESPAWN_FORBID_DURATION,
    RESPAWN_PROTECTED_DURATION,
    ActionType,
    GameMode,
)
from .grid import ConcreteGrid, Grid
from .models import Action, Game, OccupiedTile, Player, PlayerInGame
from .types import Point, Tile

logger = logging.getLogger("hexpo_game.game")


def on_maybe_tile_click(player: Player, game: Game, grid: Grid, tile: Optional[Tile]) -> Optional[PlayerInGame]:
    """Handle a click on the grid area, on a tile or not."""
    if tile is None:
        return None

    default_player_attrs = dict(  # noqa: C408
        started_turn=0,
        start_tile_col=0,
        start_tile_row=0,
        color=PALETTE[player.id % NB_COLORS].as_hex,
    )

    player_in_game = (
        PlayerInGame.objects.filter(
            player=player,
            game=game,
        )
        .order_by("-id")
        .first()
    )

    player_just_created = False
    if player_in_game is None:
        player_in_game = PlayerInGame.objects.create(
            player=player,
            game=game,
            **default_player_attrs,
        )
        player_just_created = True
    elif player_in_game.dead_at:
        if player_in_game.dead_at + RESPAWN_FORBID_DURATION > timezone.now():
            logger.warning("%s clicked on %s but IS STILL DEAD", player.name, tile)
            return player_in_game

        player_in_game = PlayerInGame.objects.create(
            player=player,
            game=game,
            **default_player_attrs,
        )
        player_just_created = True
        logger.warning("%s clicked on %s AND IS ALIVE AGAIN", player.name, tile)

    occupied_tile = (
        OccupiedTile.objects.filter(game=game, col=tile.col, row=tile.row)
        .select_related("player_in_game__player")
        .first()
    )
    if occupied_tile is not None:
        if occupied_tile.player_in_game.player_id == player.id:
            logger.info("%s clicked on %s but it's already his tile", player.name, tile)
            return player_in_game
        if timezone.now() < occupied_tile.player_in_game.started_at + RESPAWN_PROTECTED_DURATION:
            logger.info(
                "%s clicked on %s but is occupied by %s and protected",
                player.name,
                tile,
                occupied_tile.player_in_game.player.name,
            )
            return player_in_game

    if (
        game.mode == GameMode.FREE_NEIGHBOR
        and (not player_just_created or player_in_game.has_tiles())
        and not OccupiedTile.has_occupied_neighbors(player_in_game.id, tile, grid)
    ):
        logger.warning("%s clicked on %s but has no neighbors", player.name, tile)
        return player_in_game

    if occupied_tile is not None:
        old_player_in_game = occupied_tile.player_in_game
        logger.warning("%s clicked on %s that was occupied by %s", player.name, tile, old_player_in_game.player.name)
        logger.warning("%s IS NOW  DEAD", old_player_in_game.player.name)
        occupied_tile.player_in_game = player_in_game
        occupied_tile.save()

        if not old_player_in_game.has_tiles():
            old_player_in_game.die()

    else:
        logger.info("%s clicked on %s", player.name, tile)
        OccupiedTile.objects.create(game=game, col=tile.col, row=tile.row, player_in_game=player_in_game)

    logger.info("%s clicked on %s", player.name, tile)

    Action.objects.create(
        player_in_game=player_in_game,
        turn=game.current_turn,
        action_type=ActionType.GROW,
        tile_col=tile.col,
        tile_row=tile.row,
        confirmed_at=timezone.now(),
    )

    return player_in_game


async def on_click(  # pylint: disable=unused-argument
    player: Player, x_relative: float, y_relative: float, game: Game, grid: ConcreteGrid
) -> None:
    """Display a message when a click is received."""
    target, point = get_click_target(x_relative, y_relative)
    if target == "grid-area":
        area = COORDINATES["grid-area"]
        tile = grid.get_tile_at_point(Point(x=point.x - area[0][0], y=point.y - area[0][1]))

        # push this in a queue and let another process dequeue clicks in order?

        await sync_to_async(on_maybe_tile_click)(player, game, grid.grid, tile)
        if tile is not None:
            return

    logger.info("%s clicked on %s (%s)", player.name, target, point)


def get_game_and_grid() -> tuple[Game, ConcreteGrid]:
    """Get the current game."""
    area = COORDINATES["grid-area"]
    width = area[1][0] - area[0][0]
    height = area[1][1] - area[0][1]
    nb_cols, nb_rows, tile_size = ConcreteGrid.compute_grid_size(500, width, height)
    game = Game.get_current(nb_cols=nb_cols, nb_rows=nb_rows)
    grid = ConcreteGrid(Grid(nb_cols, nb_rows), tile_size)
    return game, grid
