"""Everything related to the hexagonal grid of the game.

Thanks to https://www.redblobgames.com/grids/hexagons/

We use the "odd-q" grid (flat top and top left tile filled) with the simple offset coordinate system.

"""

from __future__ import annotations

import base64
import enum
from dataclasses import dataclass, field
from math import ceil, sqrt
from textwrap import wrap
from typing import Any, Iterator, NamedTuple, Sequence, TypeAlias

import cv2  # type: ignore[import]
import numpy as np
import numpy.typing as npt


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


RenderedMap: TypeAlias = npt.NDArray[np.uint8]


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
        """Add something to a point to get another one.

        Parameters
        ----------
        other : Any
            - Can be a Point, the values of the other point will be added to the current one.
            - Any other kind of value will raise a TypeError.

        """
        if isinstance(other, Point):
            return Point(self.x + other.x, self.y + other.y)
        return NotImplemented


class Color(NamedTuple):
    """A color with red/green/blue values."""

    red: int = 0
    green: int = 0
    blue: int = 0

    @property
    def as_hex(self) -> str:
        """Return the color as a hex string."""
        return f"#{self.red:02x}{self.green:02x}{self.blue:02x}".upper()

    def as_bgr(self) -> Color:
        """Return the color as a BGR one."""
        return Color(self.blue, self.green, self.red)

    @classmethod
    def from_hex(cls, hex_color: str) -> Color:
        """Create a color from a hex string."""
        hex_color = hex_color.removeprefix("#")
        if len(hex_color) == 3:
            hex_color = f"{hex_color[0]}{hex_color[0]}{hex_color[1]}{hex_color[1]}{hex_color[2]}{hex_color[2]}"
        return Color(*[int(part, 16) for part in wrap(hex_color, 2)])


TilePoints: TypeAlias = tuple[Point, Point, Point, Point, Point, Point]


class ConcreteTile(NamedTuple):
    """Represent a concrete tile."""

    tile: Tile
    center: Point
    points: TilePoints
    points_array: npt.NDArray[np.int32] = field(repr=False, compare=False, hash=False)


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
    max_coordinates: Point = field(init=False, repr=False, compare=False, hash=False)
    map: RenderedMap = field(init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        """Create the concrete grid."""
        self.tile_width = self.tile_size * 2
        self.tile_height = self.tile_size * sqrt(3)
        self.tiles = tuple(
            tuple(
                ConcreteTile(
                    tile,
                    center := self.compute_tile_center(tile),
                    points := self.compute_tile_points(center),
                    np.array(tuple((round(point.x), round(point.y)) for point in points), dtype=np.int32),
                )
                for tile in col
            )
            for col in self.grid.tiles
        )
        self.max_coordinates = self.compute_max_coordinates()
        self.map = self.create_map()

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

    def compute_max_coordinates(self) -> Point:
        """Return the maximum coordinates of the grid."""
        last_tile_horizontal = self.tiles[0][-1]
        last_tile_vertical = self.tiles[-1][1 if self.grid.nb_cols > 1 else 0]
        return Point(last_tile_horizontal.points[1].x, last_tile_vertical.points[2].y)

    def create_map(self) -> RenderedMap:
        """Create the map of the grid.

        Returns
        -------
        RenderedMap
            The map of the grid as a 3 dimensional numpy array
            (nb pixels y, nb pixels x, 4 channels (3 colors + alpha) of uint8.

        """
        return np.zeros((ceil(self.max_coordinates.y + 1), ceil(self.max_coordinates.x + 1), 4), dtype=np.uint8)

    def reset_map(self) -> None:
        """Reset the map to 0."""
        self.map.fill(0)

    def fill_tiles(self, tiles: Sequence[Tile], color: Color) -> None:
        """Fill the area occupied by the given tiles with the given color.

        Parameters
        ----------
        tiles : Sequence[Tile]
            The tiles to fill.
        color : Color
            The color to use.

        Notes
        -----
        It's faster with `fillConvexPoly`, and even if it doesn't work with concave polygons, it's not a problem
        for hexagons.
        The code to render the same with `fillPoly` is:

        >>> cv2.fillPoly(self.map, np.stack(tuple(
        ...     self.tiles[row][col].points_array
        ...     for col, row in tiles
        ... )), tuple(color), cv2.LINE_AA)

        Optimization idea: generate a mask (values between 0 and 1) of a polygon only once and apply the mask
        multiplied by the color for each polygon.

        """
        if not tiles:
            return

        hex_map = self.create_map()

        # we only draw the tiles in the alpha channel
        for col, row in tiles:
            cv2.fillConvexPoly(  # pylint: disable=no-member
                hex_map, self.tiles[row][col].points_array, (0, 0, 0, 255), cv2.LINE_AA  # pylint: disable=no-member
            )
        # we set the same color
        mask = np.where(hex_map[:, :, 3] != 0)
        hex_map[:, :, :3] = color  # sadly we cannot do things like hex_map[mask][:,:3] = color
        # we update the map with only the pixels that are not fully transparent, i.e. where the tiles are drawn
        self.map[mask] = hex_map[mask]
