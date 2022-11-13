"""Tests for the grid package."""
import pytest

from hexpo_game.core.grid import ConcreteGrid, ConcreteTile, Grid, Point, Tile


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
    # we only test coordinates for the first point, we assume it's ok for the others
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
