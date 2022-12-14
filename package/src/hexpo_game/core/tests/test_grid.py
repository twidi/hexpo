"""Tests for the grid package."""
from itertools import product

import numpy as np
import pytest

from hexpo_game.core.grid import ConcreteGrid, ConcreteTile, Direction, Grid
from hexpo_game.core.types import Color, Point, Tile


def assert_points_equal(point1: Point, point2: Point) -> None:
    """Assert that two points are equal."""
    __tracebackhide__ = True  # pylint: disable=unused-variable
    assert point1.x == pytest.approx(point2.x)
    assert point1.y == pytest.approx(point2.y)


def test_grid() -> None:
    """Test the grid."""
    grid = Grid(3, 4)
    assert grid.nb_cols == 3
    assert grid.nb_rows == 4
    assert grid.tiles == (
        (Tile(0, 0), Tile(1, 0), Tile(2, 0)),
        (Tile(0, 1), Tile(1, 1), Tile(2, 1)),
        (Tile(0, 2), Tile(1, 2), Tile(2, 2)),
        (Tile(0, 3), Tile(1, 3), Tile(2, 3)),
    )


def test_tile_neighbors() -> None:
    """Test the neighbors of tiles."""
    grid = Grid(3, 3)
    assert grid.neighbors[Tile(0, 0)] == (None, None, Tile(1, 0), Tile(0, 1), None, None)
    assert grid.neighbors[Tile(1, 0)] == (None, Tile(2, 0), Tile(2, 1), Tile(1, 1), Tile(0, 1), Tile(0, 0))
    assert grid.neighbors[Tile(2, 0)] == (None, None, None, Tile(2, 1), Tile(1, 0), None)
    assert grid.neighbors[Tile(0, 1)] == (Tile(0, 0), Tile(1, 0), Tile(1, 1), Tile(0, 2), None, None)
    assert grid.neighbors[Tile(1, 1)] == (Tile(1, 0), Tile(2, 1), Tile(2, 2), Tile(1, 2), Tile(0, 2), Tile(0, 1))
    assert grid.neighbors[Tile(2, 1)] == (Tile(2, 0), None, None, Tile(2, 2), Tile(1, 1), Tile(1, 0))
    assert grid.neighbors[Tile(0, 2)] == (Tile(0, 1), Tile(1, 1), Tile(1, 2), None, None, None)
    assert grid.neighbors[Tile(1, 2)] == (Tile(1, 1), Tile(2, 2), None, None, None, Tile(0, 2))
    assert grid.neighbors[Tile(2, 2)] == (Tile(2, 1), None, None, None, Tile(1, 2), Tile(1, 1))


def test_point_add() -> None:
    """Test the addition of points."""
    point1 = Point(1.0, 2.0)
    point2 = Point(3.0, 4.0)
    assert_points_equal(point1 + point2, Point(4.0, 6.0))
    with pytest.raises(TypeError):
        point1 + 1.0  # pylint: disable=pointless-statement


def test_concrete_grid() -> None:
    """Test the concrete grid."""
    grid = ConcreteGrid(Grid(3, 3), 2.0)
    assert grid.tile_size == 2.0
    assert grid.tile_width == 4.0
    assert grid.tile_height == pytest.approx(3.4641016151377544)
    tiles = list(grid)
    assert len(tiles) == 9
    assert tiles[0].tile == Tile(0, 0)
    assert isinstance(tiles[0], ConcreteTile)
    assert_points_equal(tiles[0].center, Point(2, 1.7320508075688772))
    # we only test coordinates for the first two point, we assume it's ok for the others
    assert_points_equal(tiles[0].points[0], Point(3, 0))
    assert_points_equal(tiles[0].points[1], Point(4, 1.7320508075688772))
    assert_points_equal(tiles[0].points[2], Point(3, 3.4641016151377544))
    assert_points_equal(tiles[0].points[3], Point(1, 3.4641016151377544))
    assert_points_equal(tiles[0].points[4], Point(0, 1.7320508075688772))
    assert_points_equal(tiles[0].points[5], Point(1, 0))
    assert tiles[1].tile == Tile(1, 0)
    assert_points_equal(tiles[1].center, Point(5, 3.4641016151377544))
    assert tiles[2].tile == Tile(2, 0)
    assert_points_equal(tiles[2].center, Point(8, 1.7320508075688772))
    assert tiles[3].tile == Tile(0, 1)
    assert_points_equal(tiles[3].center, Point(2, 5.196152422706632))
    assert tiles[4].tile == Tile(1, 1)
    assert_points_equal(tiles[4].center, Point(5, 6.928203230275509))
    assert tiles[5].tile == Tile(2, 1)
    assert_points_equal(tiles[5].center, Point(8, 5.196152422706632))
    assert tiles[6].tile == Tile(0, 2)
    assert_points_equal(tiles[6].center, Point(2, 8.660254037844387))
    assert tiles[7].tile == Tile(1, 2)
    assert_points_equal(tiles[7].center, Point(5, 10.392304845413264))
    assert tiles[8].tile == Tile(2, 2)
    assert_points_equal(tiles[8].center, Point(8, 8.660254037844387))


def test_max_coordinates():
    """Test the max coordinates."""
    grid = ConcreteGrid(Grid(3, 4), 2.0)
    assert_points_equal(grid.max_coordinates, Point(10, 15.588457268119894))
    grid = ConcreteGrid(Grid(3, 4), 20.0)
    assert_points_equal(grid.max_coordinates, Point(100, 155.88457268119894))


def test_create_map():
    """Test the creation of a map."""
    grid = ConcreteGrid(Grid(3, 4), 2.0)
    np.testing.assert_equal(grid.map, np.zeros((17, 11, 4), dtype=np.int32))
    grid = ConcreteGrid(Grid(3, 4), 20.0)
    np.testing.assert_equal(grid.map, np.zeros((157, 101, 4), dtype=np.int32))


def test_reset_map():
    """Test the reset of a map."""
    grid = ConcreteGrid(Grid(3, 4), 2.0)
    grid.map.fill(1)
    grid.reset_map()
    np.testing.assert_equal(grid.map, np.zeros((17, 11, 4), dtype=np.int32))


def test_draw_no_tiles():
    """Test the drawing of a map with no tiles."""
    grid = ConcreteGrid(Grid(3, 4), 2.0)
    grid.reset_map()
    grid.draw_areas([], Color(240, 120, 60).as_bgr())
    np.testing.assert_equal(grid.map, np.zeros((17, 11, 4), dtype=np.int32))


def test_draw_one_tile():
    """Test the drawing of a map with one tile."""
    grid = ConcreteGrid(Grid(3, 4), 5.0)
    grid.reset_map()
    grid.draw_areas([Tile(2, 3)], Color(240, 120, 60).as_bgr())
    # first we test the area where the data is filled, then we reset this area to zero and check that everything is zero
    # pylint: disable=line-too-long
    # fmt: off
    assert grid.map[23:39, 12:26].tolist() == [
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 25], [60, 120, 240, 51], [60, 120, 240, 53], [60, 120, 240, 53], [60, 120, 240, 27], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 79], [60, 120, 240, 161], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 162], [60, 120, 240, 79], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 16], [60, 120, 240, 207], [60, 120, 240, 253], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 253], [60, 120, 240, 207], [60, 120, 240, 16]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 201], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 202]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 131], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [60, 120, 240, 115], [60, 120, 240, 247], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[60, 120, 240, 8], [60, 120, 240, 168], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 166], [60, 120, 240, 58], [60, 120, 240, 166], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [60, 120, 240, 241], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 237], [60, 120, 240, 8], [0, 0, 0, 0], [60, 120, 240, 8], [60, 120, 240, 237], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[60, 120, 240, 14], [60, 120, 240, 201], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 246], [60, 120, 240, 49], [0, 0, 0, 0], [60, 120, 240, 49], [60, 120, 240, 246], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [60, 120, 240, 124], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 217], [60, 120, 240, 65], [60, 120, 240, 217], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [60, 120, 240, 8], [60, 120, 240, 207], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 49], [60, 120, 240, 246], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 246]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 152], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 155]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 14], [60, 120, 240, 204], [60, 120, 240, 253], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 253], [60, 120, 240, 204], [60, 120, 240, 14]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 46], [60, 120, 240, 149], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 153], [60, 120, 240, 46], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 31], [60, 120, 240, 58], [60, 120, 240, 58], [60, 120, 240, 58], [60, 120, 240, 33], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
    ]
    # fmt: on
    # pylint: enable=line-too-long
    grid.map[23:39, 12:26] = 0
    np.testing.assert_equal(grid.map, np.zeros((40, 26, 4), dtype=np.int32))


def test_draw_many_tiles():
    """Test the drawing of a map with four tiles."""
    grid = ConcreteGrid(Grid(3, 4), 5.0)
    grid.reset_map()
    grid.draw_areas([Tile(1, 2), Tile(2, 2), Tile(1, 3), Tile(2, 3)], Color(240, 120, 60).as_bgr())
    # first we test the area where the data is filled, then we reset this area to zero and check that everything is zero
    # pylint: disable=line-too-long
    # fmt: off
    assert grid.map[14:40, 5:26].tolist() == [
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 46], [60, 120, 240, 79], [60, 120, 240, 120], [60, 120, 240, 69], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 10], [60, 120, 240, 200], [60, 120, 240, 243], [60, 120, 240, 255], [60, 120, 240, 178], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 152], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 201], [60, 120, 240, 4], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 49], [60, 120, 240, 246], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 199], [60, 120, 240, 12], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 8], [60, 120, 240, 207], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 124], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 124], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 207], [60, 120, 240, 8], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 80], [60, 120, 240, 115], [60, 120, 240, 125]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 10], [60, 120, 240, 197], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 247], [60, 120, 240, 49], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 16], [60, 120, 240, 207], [60, 120, 240, 248], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 252], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 250], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 201], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 26], [60, 120, 240, 228], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 216], [60, 120, 240, 95], [60, 120, 240, 177], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 182], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 203], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 16], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 210]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 48], [60, 120, 240, 92], [60, 120, 240, 95], [60, 120, 240, 95], [60, 120, 240, 217], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 254], [60, 120, 240, 213], [60, 120, 240, 22]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 12], [60, 120, 240, 173], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 205], [60, 120, 240, 79], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 8], [60, 120, 240, 181], [60, 120, 240, 253], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 224], [60, 120, 240, 103], [60, 120, 240, 103], [60, 120, 240, 62], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 80], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 254], [60, 120, 240, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [60, 120, 240, 6], [60, 120, 240, 197], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 89], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [60, 120, 240, 51], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 246], [60, 120, 240, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [60, 120, 240, 155], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 134], [60, 120, 240, 111], [60, 120, 240, 249], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 189], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[60, 120, 240, 14], [60, 120, 240, 214], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 197], [60, 120, 240, 6], [0, 0, 0, 0], [60, 120, 240, 89], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 242], [60, 120, 240, 20], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[60, 120, 240, 14], [60, 120, 240, 215], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 82], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 246], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 252], [60, 120, 240, 12], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[60, 120, 240, 2], [60, 120, 240, 8], [60, 120, 240, 193], [60, 120, 240, 255], [60, 120, 240, 233], [60, 120, 240, 183], [60, 120, 240, 10], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 131], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 179], [60, 120, 240, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 77], [60, 120, 240, 255], [60, 120, 240, 77], [60, 120, 240, 12], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 115], [60, 120, 240, 246], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 250], [60, 120, 240, 118], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 8], [60, 120, 240, 168], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 140], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 196], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 206], [60, 120, 240, 8], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
    ]
    # fmt: on
    # pylint: enable=line-too-long
    grid.map[14:40, 5:26] = 0
    np.testing.assert_equal(grid.map, np.zeros((40, 26, 4), dtype=np.int32))


def test_draw_many_areas():
    """Test many drawings on a map"""
    grid = ConcreteGrid(Grid(3, 4), 5.0)
    grid.reset_map()
    grid.draw_areas([Tile(0, 1)], Color(60, 240, 120).as_bgr())
    grid.draw_areas([Tile(2, 3)], Color(240, 120, 60).as_bgr())
    # first we test the area where the data is filled, then we reset this area to zero and check that everything is zero
    # pylint: disable=line-too-long
    # fmt: off
    assert grid.map[6:21, 0:14].tolist() == [
        [[0, 0, 0, 0], [0, 0, 0, 0], [120, 240, 60, 25], [120, 240, 60, 51], [120, 240, 60, 53], [120, 240, 60, 53], [120, 240, 60, 53], [120, 240, 60, 53], [120, 240, 60, 27], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[120, 240, 60, 23], [120, 240, 60, 136], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 134], [120, 240, 60, 23], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[120, 240, 60, 167], [120, 240, 60, 250], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 251], [120, 240, 60, 196], [120, 240, 60, 8], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 119], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 230], [120, 240, 60, 20], [0, 0, 0, 0]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 131], [0, 0, 0, 0]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 236], [120, 240, 60, 73], [120, 240, 60, 58], [120, 240, 60, 73], [120, 240, 60, 235], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 205], [120, 240, 60, 10]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 181], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [120, 240, 60, 178], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 246], [120, 240, 60, 20]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 234], [120, 240, 60, 69], [120, 240, 60, 53], [120, 240, 60, 69], [120, 240, 60, 236], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 209], [120, 240, 60, 14]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 131], [0, 0, 0, 0]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 229], [120, 240, 60, 20], [0, 0, 0, 0]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 119], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[120, 240, 60, 172], [120, 240, 60, 251], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 252], [120, 240, 60, 200], [120, 240, 60, 12], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[120, 240, 60, 23], [120, 240, 60, 147], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 147], [120, 240, 60, 23], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [120, 240, 60, 31], [120, 240, 60, 58], [120, 240, 60, 58], [120, 240, 60, 58], [120, 240, 60, 58], [120, 240, 60, 58], [120, 240, 60, 33], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
    ]
    assert grid.map[23:39, 12:26].tolist() == [
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 25], [60, 120, 240, 51], [60, 120, 240, 53], [60, 120, 240, 53], [60, 120, 240, 27], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 79], [60, 120, 240, 161], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 162], [60, 120, 240, 79], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 16], [60, 120, 240, 207], [60, 120, 240, 253], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 253], [60, 120, 240, 207], [60, 120, 240, 16]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 201], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 202]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 131], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [60, 120, 240, 115], [60, 120, 240, 247], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[60, 120, 240, 8], [60, 120, 240, 168], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 166], [60, 120, 240, 58], [60, 120, 240, 166], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [60, 120, 240, 241], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 237], [60, 120, 240, 8], [0, 0, 0, 0], [60, 120, 240, 8], [60, 120, 240, 237], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[60, 120, 240, 14], [60, 120, 240, 201], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 246], [60, 120, 240, 49], [0, 0, 0, 0], [60, 120, 240, 49], [60, 120, 240, 246], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [60, 120, 240, 124], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 217], [60, 120, 240, 65], [60, 120, 240, 217], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [60, 120, 240, 8], [60, 120, 240, 207], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 49], [60, 120, 240, 246], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 246]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 152], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 155]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 14], [60, 120, 240, 204], [60, 120, 240, 253], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 253], [60, 120, 240, 204], [60, 120, 240, 14]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 46], [60, 120, 240, 149], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 153], [60, 120, 240, 46], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 31], [60, 120, 240, 58], [60, 120, 240, 58], [60, 120, 240, 58], [60, 120, 240, 33], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
    ]
    # fmt: on
    # pylint: enable=line-too-long
    grid.map[6:21, 0:14] = 0
    grid.map[23:39, 12:26] = 0
    np.testing.assert_equal(grid.map, np.zeros((40, 26, 4), dtype=np.int32))


def test_map_as_base64_png():
    """Test rendering map as a base64 encoded PNG."""
    grid = ConcreteGrid(Grid(3, 4), 5.0)
    grid.reset_map()
    grid.draw_areas([Tile(0, 1)], Color(60, 240, 120).as_bgr())
    grid.draw_areas([Tile(2, 3)], Color(240, 120, 60).as_bgr())

    # pylint: disable=line-too-long
    # fmt: off
    assert grid.map_as_base64_png() == 'iVBORw0KGgoAAAANSUhEUgAAABoAAAAoCAYAAADg+OpoAAACJElEQVRYCb3BMWhdVQAA0HODQrrEiwqlDdjNMZqli7eD0k2koIOI6FqRLuLgHdKpAW9HoUIRB9Ehiw7t4CLocosUxUJGl05JKEa5FTEdtM/BD+nnE/Lf++WdE4wkGEkwkmAkwUiCkQQTqeVTOI0l03ZrLDsWFFLLJ/EBPnK0j/FJjeWegUJqeQtv4ElH+we3cb7G8sAAIbXcmV+usVw1QEgtd+a3h7Uay76eQmq5089mjeWynkJquXPod7yD+3gKX+JZ037BuRrL33oIqeXOoW9rLK+aSC3fxGumHeC5Gsu+HkJquXPoN7yNhogtPGPaNs7VWP7UQ0gtd/rZrLFc1lNILXfmt4sXaiz7egqp5c78co3lqgFCavlrXMATjvYvfsb5GstfBgip5ZPYwCVHu4bNGss9AwUTqeUzWDVrr8Zy14KCkQQjCR6TltMpnMaS/+3GUndMBAtqOV3A63jXrK/wTSz1RrCAllPED1jDklkPsY2XgwW0nG7jrOP9FAzUcrqCDXMKBmg5fYhNLJtT0FPLaRlf4E2ztnANl/CWRwQDtJzuY8W0P7AaS33QclrGDp42EfTUclrBdzhr2gFeiqXeaTmt4xZOmAgGaDlt4IpZv+I9XMfzHhEM0HJaxo940ZyCgVpO67iFE453ECyg5XQdFx3v82ABLacVfI91LJn1EHfwSrCgltMaLuJ9sz7Dp7HU7eAxaTmdwapDe7HUuyaCkfwHKjetS4moZhYAAAAASUVORK5CYII='
    # fmt: on
    # pylint: enable=line-too-long


def test_compute_tile_size():
    """Test computing the tile size."""
    tile_size = ConcreteGrid.compute_tile_size(41, 24, 1920, 1280)
    assert tile_size == pytest.approx(30.068674469320158)


def test_compute_grid_size():
    """Test computing the grid size."""
    nb_cols, nb_rows, tile_size = ConcreteGrid.compute_grid_size(1000, 1920, 1280)
    assert nb_cols == 41
    assert nb_rows == 24
    assert tile_size == pytest.approx(30.068674469320158)
    grid = ConcreteGrid(Grid(nb_cols, nb_rows), tile_size)
    assert grid.max_coordinates.x == pytest.approx(1864.2578170978495)
    assert grid.max_coordinates.y == pytest.approx(1275.9715614792356)


def test_get_tile_at_point():  # pylint: disable=too-many-statements
    """Test getting the tile at a point."""
    grid = ConcreteGrid(Grid(2, 2), 20.0)
    assert grid.get_tile_at_point(Point(0, 0)) is None

    # perimeter points

    point = grid.tiles[0][0].points[5]
    assert grid.get_tile_at_point(Point(point.x - 2, point.y)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y - 2)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y + 2)) == Tile(0, 0)

    point = grid.tiles[0][0].points[0]
    assert grid.get_tile_at_point(Point(point.x, point.y - 2)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y)) is None
    assert grid.get_tile_at_point(Point(point.x, point.y + 2)) == Tile(0, 0)

    point = grid.tiles[0][0].points[1]
    assert grid.get_tile_at_point(Point(point.x - 2, point.y)) == Tile(0, 0)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y - 2)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y + 2)) == Tile(1, 0)

    point = grid.tiles[0][1].points[0]
    assert grid.get_tile_at_point(Point(point.x, point.y - 2)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y)) is None
    assert grid.get_tile_at_point(Point(point.x, point.y + 2)) == Tile(1, 0)

    point = grid.tiles[0][1].points[1]
    assert grid.get_tile_at_point(Point(point.x - 2, point.y)) == Tile(1, 0)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y - 2)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y + 2)) is None

    point = grid.tiles[0][1].points[2]
    assert grid.get_tile_at_point(Point(point.x, point.y - 2)) == Tile(1, 0)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y)) is None
    assert grid.get_tile_at_point(Point(point.x, point.y + 2)) == Tile(1, 1)

    point = grid.tiles[1][1].points[1]
    assert grid.get_tile_at_point(Point(point.x - 2, point.y)) == Tile(1, 1)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y - 2)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y + 2)) is None

    point = grid.tiles[1][1].points[2]
    assert grid.get_tile_at_point(Point(point.x, point.y - 2)) == Tile(1, 1)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y)) is None
    assert grid.get_tile_at_point(Point(point.x, point.y + 2)) is None

    point = grid.tiles[1][1].points[3]
    assert grid.get_tile_at_point(Point(point.x - 2, point.y)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y - 2)) == Tile(1, 1)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y + 2)) is None

    point = grid.tiles[1][1].points[4]
    assert grid.get_tile_at_point(Point(point.x, point.y - 2)) == Tile(0, 1)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y)) == Tile(1, 1)
    assert grid.get_tile_at_point(Point(point.x, point.y + 2)) is None

    point = grid.tiles[1][0].points[3]
    assert grid.get_tile_at_point(Point(point.x - 2, point.y)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y - 2)) == Tile(0, 1)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y + 2)) is None

    point = grid.tiles[1][0].points[4]
    assert grid.get_tile_at_point(Point(point.x, point.y - 2)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y)) == Tile(0, 1)
    assert grid.get_tile_at_point(Point(point.x, point.y + 2)) is None

    point = grid.tiles[1][0].points[5]
    assert grid.get_tile_at_point(Point(point.x - 2, point.y)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y - 2)) == Tile(0, 0)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y + 2)) == Tile(0, 1)

    point = grid.tiles[0][0].points[4]
    assert grid.get_tile_at_point(Point(point.x, point.y - 2)) is None
    assert grid.get_tile_at_point(Point(point.x + 2, point.y)) == Tile(0, 0)
    assert grid.get_tile_at_point(Point(point.x, point.y + 2)) is None

    # now center points
    point = grid.tiles[0][0].points[2]
    assert grid.get_tile_at_point(Point(point.x, point.y - 2)) == Tile(0, 0)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y)) == Tile(1, 0)
    assert grid.get_tile_at_point(Point(point.x, point.y + 2)) == Tile(0, 1)

    point = grid.tiles[1][0].points[1]
    assert grid.get_tile_at_point(Point(point.x - 2, point.y)) == Tile(0, 1)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y - 2)) == Tile(1, 0)
    assert grid.get_tile_at_point(Point(point.x + 2, point.y + 2)) == Tile(1, 1)


def test_get_border_tiles_single_tile():
    """Test get_border_tiles with a single tile."""
    grid = Grid(5, 5)
    border_tiles = grid.get_border_tiles([Tile(0, 0)])
    assert border_tiles == {
        Tile(0, 0): {
            Direction.NORTH,
            Direction.NORTH_EAST,
            Direction.SOUTH_EAST,
            Direction.SOUTH,
            Direction.SOUTH_WEST,
            Direction.NORTH_WEST,
        },
    }


def test_get_border_tiles_single_area():
    """Test get_border_tiles with a single area."""
    grid = Grid(5, 5)
    border_tiles = grid.get_border_tiles([Tile(col, row) for col, row in product(range(3), range(3))])
    assert border_tiles == {
        Tile(0, 0): {Direction.NORTH, Direction.NORTH_EAST, Direction.SOUTH_WEST, Direction.NORTH_WEST},
        Tile(1, 0): {Direction.NORTH},
        Tile(2, 0): {Direction.NORTH, Direction.NORTH_EAST, Direction.SOUTH_EAST, Direction.NORTH_WEST},
        Tile(0, 1): {Direction.NORTH_WEST, Direction.SOUTH_WEST},
        Tile(2, 1): {Direction.NORTH_EAST, Direction.SOUTH_EAST},
        Tile(0, 2): {Direction.SOUTH, Direction.SOUTH_WEST, Direction.NORTH_WEST},
        Tile(1, 2): {Direction.SOUTH_EAST, Direction.SOUTH, Direction.SOUTH_WEST},
        Tile(2, 2): {Direction.NORTH_EAST, Direction.SOUTH_EAST, Direction.SOUTH},
    }


def test_get_border_tiles_multiple_areas():
    """Test get_border_tiles with multiple areas."""
    grid = Grid(10, 10)
    border_tiles = grid.get_border_tiles(
        [Tile(col, row) for col, row in product(range(3), range(3))]
        + [Tile(col, row) for col, row in product(range(4, 7), range(4, 7))]
    )
    assert border_tiles == {
        Tile(0, 0): {Direction.NORTH, Direction.NORTH_EAST, Direction.SOUTH_WEST, Direction.NORTH_WEST},
        Tile(1, 0): {Direction.NORTH},
        Tile(2, 0): {Direction.NORTH, Direction.NORTH_EAST, Direction.SOUTH_EAST, Direction.NORTH_WEST},
        Tile(0, 1): {Direction.NORTH_WEST, Direction.SOUTH_WEST},
        Tile(2, 1): {Direction.NORTH_EAST, Direction.SOUTH_EAST},
        Tile(0, 2): {Direction.SOUTH, Direction.SOUTH_WEST, Direction.NORTH_WEST},
        Tile(1, 2): {Direction.SOUTH_EAST, Direction.SOUTH, Direction.SOUTH_WEST},
        Tile(2, 2): {Direction.NORTH_EAST, Direction.SOUTH_EAST, Direction.SOUTH},
        Tile(4, 4): {Direction.NORTH, Direction.NORTH_EAST, Direction.SOUTH_WEST, Direction.NORTH_WEST},
        Tile(5, 4): {Direction.NORTH},
        Tile(6, 4): {Direction.NORTH, Direction.NORTH_EAST, Direction.SOUTH_EAST, Direction.NORTH_WEST},
        Tile(4, 5): {Direction.NORTH_WEST, Direction.SOUTH_WEST},
        Tile(6, 5): {Direction.NORTH_EAST, Direction.SOUTH_EAST},
        Tile(4, 6): {Direction.SOUTH, Direction.SOUTH_WEST, Direction.NORTH_WEST},
        Tile(5, 6): {Direction.SOUTH_EAST, Direction.SOUTH, Direction.SOUTH_WEST},
        Tile(6, 6): {Direction.NORTH_EAST, Direction.SOUTH_EAST, Direction.SOUTH},
    }
