"""Main game loop and functions."""

import logging

from asgiref.sync import sync_to_async
from django.utils import timezone

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .click_handler import COORDINATES, get_click_target
from .constants import NB_COLORS, ActionType, GameMode, PALETTE
from .grid import ConcreteGrid, Grid
from .models import Action, Game, OccupiedTile, Player, PlayerInGame
from .types import Point

logger = logging.getLogger("hexpo_game.game")


async def on_click(  # pylint: disable=unused-argument
    player: Player, x_relative: float, y_relative: float, game: Game, grid: ConcreteGrid
) -> None:
    """Display a message when a click is received."""
    target, point = get_click_target(x_relative, y_relative)
    if target == "grid-area":
        area = COORDINATES["grid-area"]
        tile = grid.get_tile_at_point(Point(x=point.x - area[0][0], y=point.y - area[0][1]))
        if tile is not None:

            player_in_game, _ = await PlayerInGame.objects.aget_or_create(
                player=player,
                game=game,
                defaults=dict(  # noqa: C408
                    started_turn=0,
                    start_tile_col=0,
                    start_tile_row=0,
                    color=PALETTE[player.id % NB_COLORS].as_hex,
                ),
            )

            if (
                game.mode == GameMode.FREE_NEIGHBOR
                and await sync_to_async(OccupiedTile.has_tiles)(player_in_game.id)
                and not await sync_to_async(OccupiedTile.has_occupied_neighbors)(player_in_game.id, tile, grid.grid)
            ):
                logger.warning("%s clicked on %s (%s) but has no neighbors", player.name, tile, point)
                return

            logger.info("%s clicked on %s (%s)", player.name, tile, point)

            await OccupiedTile.objects.aupdate_or_create(
                game=game,
                col=tile.col,
                row=tile.row,
                defaults=dict(  # noqa: C408
                    player_in_game=player_in_game,
                ),
            )

            await Action.objects.acreate(
                player_in_game=player_in_game,
                turn=game.current_turn,
                action_type=ActionType.GROW,
                tile_col=tile.col,
                tile_row=tile.row,
                confirmed_at=timezone.now(),
            )
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
