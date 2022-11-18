"""Tests for the grid package."""

import numpy as np
import pytest

from hexpo_game.core.grid import Color, ConcreteGrid, ConcreteTile, Grid, Point, Tile


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
    assert grid.neighbors[Tile(0, 0)] == (Tile(1, 0), Tile(0, 1))
    assert grid.neighbors[Tile(1, 0)] == (Tile(2, 0), Tile(2, 1), Tile(1, 1), Tile(0, 1), Tile(0, 0))
    assert grid.neighbors[Tile(2, 0)] == (Tile(2, 1), Tile(1, 0))
    assert grid.neighbors[Tile(0, 1)] == (Tile(0, 0), Tile(1, 0), Tile(1, 1), Tile(0, 2))
    assert grid.neighbors[Tile(1, 1)] == (Tile(1, 0), Tile(2, 1), Tile(2, 2), Tile(1, 2), Tile(0, 2), Tile(0, 1))
    assert grid.neighbors[Tile(2, 1)] == (Tile(2, 0), Tile(2, 2), Tile(1, 1), Tile(1, 0))
    assert grid.neighbors[Tile(0, 2)] == (Tile(0, 1), Tile(1, 1), Tile(1, 2))
    assert grid.neighbors[Tile(1, 2)] == (Tile(1, 1), Tile(2, 2), Tile(0, 2))
    assert grid.neighbors[Tile(2, 2)] == (Tile(2, 1), Tile(1, 2), Tile(1, 1))


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
    np.testing.assert_equal(tiles[0].points_array, np.array([[3, 0], [4, 2], [3, 3], [1, 3], [0, 2], [1, 0]]))
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


def test_fill_no_tiles():
    """Test the fill of a map with no tiles."""
    grid = ConcreteGrid(Grid(3, 4), 2.0)
    grid.reset_map()
    grid.fill_tiles([], Color(240, 120, 60).as_bgr())
    np.testing.assert_equal(grid.map, np.zeros((17, 11, 4), dtype=np.int32))


def test_fill_one_tile():
    """Test the fill of a map with one tile."""
    grid = ConcreteGrid(Grid(3, 4), 5.0)
    grid.reset_map()
    grid.fill_tiles([Tile(2, 3)], Color(240, 120, 60).as_bgr())
    # first we test the area where the data is filled, then we reset this area to zero and check that everything is zero
    # pylint: disable=line-too-long
    # fmt: off
    assert grid.map[25:37, 14:26].tolist() == [
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 25], [60, 120, 240, 51], [60, 120, 240, 53], [60, 120, 240, 53], [60, 120, 240, 27], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 31], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 37], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 23], [60, 120, 240, 239], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 239], [60, 120, 240, 23], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 201], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 201], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [60, 120, 240, 131], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 131]],
        [[60, 120, 240, 58], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[60, 120, 240, 4], [60, 120, 240, 167], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 167]],
        [[0, 0, 0, 0], [60, 120, 240, 29], [60, 120, 240, 240], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 240], [60, 120, 240, 29]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 116], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 116], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 12], [60, 120, 240, 218], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 218], [60, 120, 240, 12], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 35], [60, 120, 240, 217], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 37], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 31], [60, 120, 240, 62], [60, 120, 240, 58], [60, 120, 240, 61], [60, 120, 240, 33], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
    ]
    # fmt: on
    # pylint: enable=line-too-long
    grid.map[25:37, 14:26] = 0
    np.testing.assert_equal(grid.map, np.zeros((40, 26, 4), dtype=np.int32))


def test_fill_many_tiles():
    """Test the fill of a map with four tiles."""
    grid = ConcreteGrid(Grid(3, 4), 5.0)
    grid.reset_map()
    grid.fill_tiles([Tile(1, 2), Tile(2, 2), Tile(1, 3), Tile(2, 3)], Color(240, 120, 60).as_bgr())
    # first we test the area where the data is filled, then we reset this area to zero and check that everything is zero
    # pylint: disable=line-too-long
    # fmt: off
    assert grid.map[16:40, 7:26].tolist() == [
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 25], [60, 120, 240, 51], [60, 120, 240, 53], [60, 120, 240, 53], [60, 120, 240, 27], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 29], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 35], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 12], [60, 120, 240, 216], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 216], [60, 120, 240, 12], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 116], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 116], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 29], [60, 120, 240, 240], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 240], [60, 120, 240, 29]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 25], [60, 120, 240, 51], [60, 120, 240, 53], [60, 120, 240, 53], [60, 120, 240, 53], [60, 120, 240, 178], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 169]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 29], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 184], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 139]],
        [[0, 0, 0, 0], [60, 120, 240, 58], [60, 120, 240, 242], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 209], [60, 120, 240, 8]],
        [[0, 0, 0, 0], [60, 120, 240, 187], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 244], [60, 120, 240, 27], [0, 0, 0, 0]],
        [[60, 120, 240, 56], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 71], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[60, 120, 240, 8], [60, 120, 240, 192], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 239], [60, 120, 240, 23], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [60, 120, 240, 65], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 201], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [60, 120, 240, 6], [60, 120, 240, 194], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 131]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 58], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 157], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 167]],
        [[0, 0, 0, 0], [60, 120, 240, 27], [60, 120, 240, 231], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 240], [60, 120, 240, 29]],
        [[0, 0, 0, 0], [60, 120, 240, 109], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 116], [0, 0, 0, 0]],
        [[60, 120, 240, 12], [60, 120, 240, 209], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 218], [60, 120, 240, 12], [0, 0, 0, 0]],
        [[60, 120, 240, 54], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 37], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[60, 120, 240, 8], [60, 120, 240, 192], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 152], [60, 120, 240, 64], [60, 120, 240, 58], [60, 120, 240, 61], [60, 120, 240, 33], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [60, 120, 240, 65], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 209], [60, 120, 240, 8], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [60, 120, 240, 6], [60, 120, 240, 194], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 244], [60, 120, 240, 27], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 35], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 40], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
    ]
    # fmt: on
    # pylint: enable=line-too-long
    grid.map[16:40, 7:26] = 0
    np.testing.assert_equal(grid.map, np.zeros((40, 26, 4), dtype=np.int32))


def test_fill_many_areas():
    """Test many fills of a map"""
    grid = ConcreteGrid(Grid(3, 4), 5.0)
    grid.reset_map()
    grid.fill_tiles([Tile(0, 1)], Color(60, 240, 120).as_bgr())
    grid.fill_tiles([Tile(2, 3)], Color(240, 120, 60).as_bgr())
    # first we test the area where the data is filled, then we reset this area to zero and check that everything is zero
    # pylint: disable=line-too-long
    # fmt: off
    assert grid.map[8:19, 0:12].tolist() == [
        [[0, 0, 0, 0], [0, 0, 0, 0], [120, 240, 60, 25], [120, 240, 60, 51], [120, 240, 60, 53], [120, 240, 60, 53], [120, 240, 60, 53], [120, 240, 60, 53], [120, 240, 60, 27], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [120, 240, 60, 29], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 35], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [120, 240, 60, 184], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 184], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[120, 240, 60, 58], [120, 240, 60, 242], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 58], [0, 0, 0, 0]],
        [[120, 240, 60, 187], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 187], [0, 0, 0, 0]],
        [[120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 60]],
        [[120, 240, 60, 192], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 192], [120, 240, 60, 8]],
        [[120, 240, 60, 65], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 65], [0, 0, 0, 0]],
        [[120, 240, 60, 6], [120, 240, 60, 194], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 194], [120, 240, 60, 6], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [120, 240, 60, 35], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 255], [120, 240, 60, 37], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [120, 240, 60, 31], [120, 240, 60, 60], [120, 240, 60, 58], [120, 240, 60, 58], [120, 240, 60, 58], [120, 240, 60, 60], [120, 240, 60, 33], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    ]
    assert grid.map[25:37, 14:26].tolist() == [
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 25], [60, 120, 240, 51], [60, 120, 240, 53], [60, 120, 240, 53], [60, 120, 240, 27], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 31], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 37], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 23], [60, 120, 240, 239], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 239], [60, 120, 240, 23], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 201], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 201], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [60, 120, 240, 131], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 131]],
        [[60, 120, 240, 58], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255]],
        [[60, 120, 240, 4], [60, 120, 240, 167], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 167]],
        [[0, 0, 0, 0], [60, 120, 240, 29], [60, 120, 240, 240], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 240], [60, 120, 240, 29]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 116], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 116], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 12], [60, 120, 240, 218], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 218], [60, 120, 240, 12], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 35], [60, 120, 240, 217], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 255], [60, 120, 240, 37], [0, 0, 0, 0], [0, 0, 0, 0]],
        [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [60, 120, 240, 31], [60, 120, 240, 62], [60, 120, 240, 58], [60, 120, 240, 61], [60, 120, 240, 33], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
    ]
    # fmt: on
    # pylint: enable=line-too-long
    grid.map[8:19, 0:12] = 0
    grid.map[25:37, 14:26] = 0
    np.testing.assert_equal(grid.map, np.zeros((40, 26, 4), dtype=np.int32))


def test_map_as_base64_png():
    """Test rendering map as a base64 encoded PNG."""
    grid = ConcreteGrid(Grid(3, 4), 5.0)
    grid.reset_map()
    grid.fill_tiles([Tile(0, 1)], Color(60, 240, 120).as_bgr())
    grid.fill_tiles([Tile(2, 3)], Color(240, 120, 60).as_bgr())

    # pylint: disable=line-too-long
    # fmt: off
    assert grid.map_as_base64_png() == 'iVBORw0KGgoAAAANSUhEUgAAABoAAAAoCAYAAADg+OpoAAABmElEQVRYCb3Bv2pUURDA4d+sYqVkOklg2SJmsbGxUIgTRImYR/BBFKaw0+KAvoWNTyARg3/wKGhhYyOsEhE3YDcBiyCiXnBBwnK94Z7lfJ9QiVCJUIlQiVCJUIlQiVCJMGPhy8AKMOCwvaxpSiGhYeFD4AvtzmRNnyggNCx8G7hOu8dZ0xYFxMLXgW3gFP93KWt6TU9i4U+ATbrtZE3X6Eks/DdHt5E1ZXoQC38OXKbbC2ArazqgB7HwK8BTul3Nmp7Rk1j4CWAH2KDdS2Aza/pBT0LDwleBj7QbZ00TCggzFj4ChsAv/hkA06xpl0JCJUIlQiVCJUIlQiXCgoTbMrACDPhrT1OeMiMsQLiNgM/MG2vKExpCoXA7DXwAlHkBnNWUvwmFwu0NcIF2bzXli0KBcLsD3KbbXaGncFsHXnFEQk/hdhx4ANyg20OhQLgNgffAEu32gXNCoXC7Cdyj3S1N+b5QKNxOAu+ANeZNgPOa8ndhAcJtFXgEjDlsrClPaAgLEm4jYAT8BI4BXzXlXWaESoRKhEr+AGY/cf+pFmQeAAAAAElFTkSuQmCC'
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
