"""Everything related to the hexagonal grid of the game.

Thanks to https://www.redblobgames.com/grids/hexagons/

We use the "odd-q" grid (flat top and top left tile filled) with the simple offset coordinate system.

"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from math import sqrt
from typing import Any, Iterator, NamedTuple, TypeAlias


class Tile(NamedTuple):
    """Represent a tile."""

    col: int
    row: int


class Direction(enum.IntEnum):
    """Represent a direction in the grid."""

    NORTH = 0
    NORTH_EAST = 1
    SOUTH_EAST = 2
    SOUTH = 3
    SOUTH_WEST = 4
    NORTH_WEST = 5


DIRECTION_DIFFERENCES = (
    # even cols
    [Tile(0, -1), Tile(1, -1), Tile(1, 0), Tile(0, 1), Tile(-1, 0), Tile(-1, -1)],
    # odd cols
    [Tile(0, -1), Tile(1, 0), Tile(1, 1), Tile(0, 1), Tile(-1, 1), Tile(-1, 0)],
)


@dataclass
class Grid:
    """Represent a grid of tiles for the game."""

    nb_cols: int
    nb_rows: int
    tiles: tuple[tuple[Tile, ...], ...] = field(
        default_factory=tuple, init=False, repr=False, compare=False, hash=False
    )
    neighbors: dict[Tile, tuple[Tile, ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        """Create the grid."""
        self.tiles = tuple(tuple(Tile(col, row) for col in range(self.nb_cols)) for row in range(self.nb_rows))
        self.neighbors = {tile: self.compute_neighbors(tile) for tile in self}

    def __iter__(self) -> Iterator[Tile]:
        """Iterate over the tiles."""
        for row in self.tiles:
            yield from row

    def compute_neighbors(self, tile: Tile) -> tuple[Tile, ...]:
        """Return the neighbors of a tile."""
        neighbors: list[Tile] = []
        for direction in Direction:
            col_diff, row_diff = DIRECTION_DIFFERENCES[tile.col % 2][direction.value]
            col = tile.col + col_diff
            row = tile.row + row_diff
            if 0 <= col < self.nb_cols and 0 <= row < self.nb_rows:
                neighbors.append(self.tiles[row][col])
        return tuple(neighbors)


class Point(NamedTuple):
    """Represent a point in the grid."""

    x: float
    y: float

    def __add__(self, other: Any) -> Point:
        """Add two points."""
        if isinstance(other, Point):
            return Point(self.x + other.x, self.y + other.y)
        return NotImplemented


TilePoints: TypeAlias = tuple[Point, Point, Point, Point, Point, Point]


class ConcreteTile(NamedTuple):
    """Represent a concrete tile."""

    tile: Tile
    center: Point
    points: TilePoints


@dataclass
class ConcreteGrid:
    """Represent a concrete grid."""

    grid: Grid
    tile_size: float
    tile_width: float = field(init=False, repr=False, compare=False, hash=False)
    tile_height: float = field(init=False, repr=False, compare=False, hash=False)
    tiles: tuple[tuple[ConcreteTile, ...], ...] = field(
        default_factory=tuple, init=False, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        """Create the concrete grid."""
        self.tile_width = self.tile_size * 2
        self.tile_height = self.tile_size * sqrt(3)
        self.tiles = tuple(
            tuple(
                ConcreteTile(
                    tile,
                    center := self.compute_tile_center(tile),
                    self.compute_tile_points(center),
                )
                for tile in col
            )
            for col in self.grid.tiles
        )

    def __iter__(self) -> Iterator[ConcreteTile]:
        """Iterate over the concrete tiles."""
        for row in self.tiles:
            yield from row

    def compute_tile_center(self, tile: Tile) -> Point:
        """Compute the center of a tile.

        Center is moved top/left by half a tile to have the top/left of
        the rectangle containing the Tile(0, 0) to be at (0, 0).
        """
        return Point(
            self.tile_size * 3 / 2 * tile.col + self.tile_width * 1 / 2,
            self.tile_size * sqrt(3) * (tile.row + 0.5 * (tile.col % 2)) + self.tile_height * 1 / 2,
        )

    def compute_tile_points(self, center: Point) -> TilePoints:
        """Compute the points of a tile from its center."""
        return (
            Point(center.x + self.tile_width * 1 / 4, center.y - self.tile_height * 1 / 2),
            Point(center.x + self.tile_width * 1 / 2, center.y),
            Point(center.x + self.tile_width * 1 / 4, center.y + self.tile_height * 1 / 2),
            Point(center.x - self.tile_width * 1 / 4, center.y + self.tile_height * 1 / 2),
            Point(center.x - self.tile_width * 1 / 2, center.y),
            Point(center.x - self.tile_width * 1 / 4, center.y - self.tile_height * 1 / 2),
        )
