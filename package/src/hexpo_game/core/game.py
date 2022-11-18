"""Main game loop and functions."""

import logging

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .click_handler import COORDINATES, get_click_target
from .grid import ConcreteGrid, Grid
from .models import Game
from .types import Point

logger = logging.getLogger("hexpo_game.game")


def on_click(  # pylint: disable=unused-argument
    username: str, x_relative: float, y_relative: float, game: Game, grid: ConcreteGrid
) -> None:
    """Display a message when a click is received."""
    target, point = get_click_target(x_relative, y_relative)
    if target == "grid-area":
        area = COORDINATES["grid-area"]
        tile = grid.get_tile_at_point(Point(x=point.x - area[0][0], y=point.y - area[0][1]))
        if tile is not None:
            logger.info("%s clicked on %s (%s)", username, tile, point)
            return
    logger.info("%s clicked on %s (%s)", username, target, point)


def get_game_and_grid() -> tuple[Game, ConcreteGrid]:
    """Get the current game."""
    area = COORDINATES["grid-area"]
    width = area[1][0] - area[0][0]
    height = area[1][1] - area[0][1]
    nb_cols, nb_rows, tile_size = ConcreteGrid.compute_grid_size(500, width, height)
    game = Game.get_current(nb_cols=nb_cols, nb_rows=nb_rows)
    grid = ConcreteGrid(Grid(nb_cols, nb_rows), tile_size)
    return game, grid
