"""Everything related to the hexagonal grid of the game.

Thanks to https://www.redblobgames.com/grids/hexagons/

We use the "odd-q" grid (flat top and top left tile filled) with the simple offset coordinate system.

"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field
from itertools import chain
from math import ceil, floor, sqrt
from typing import Iterable, Iterator, NamedTuple, Optional, TypeAlias

import cv2  # type: ignore[import]
import numpy as np
import numpy.typing as npt

from .constants import PALETTE_BGR
from .types import AxialCoordinate, Color, Point, Tile

SQRT3 = sqrt(3)
HEX_WIDTH_TO_HEIGHT_RATIO = SQRT3 / 2  # height = width * HEX_WIDTH_TO_HEIGHT_RATIO

THICKNESS = 3
SEGMENTS_OFFSET = 10
SEGMENTS_OFFSET_X = SEGMENTS_OFFSET / 2
SEGMENTS_OFFSET_Y = SEGMENTS_OFFSET * SQRT3 / 2
SEGMENTS_OFFSETS: tuple[
    tuple[Point, Point],
    tuple[Point, Point],
    tuple[Point, Point],
    tuple[Point, Point],
    tuple[Point, Point],
    tuple[Point, Point],
] = (
    # north
    (Point(SEGMENTS_OFFSET_X, SEGMENTS_OFFSET_Y), Point(-SEGMENTS_OFFSET_X, SEGMENTS_OFFSET_Y)),
    # north_east
    (Point(-SEGMENTS_OFFSET_X, SEGMENTS_OFFSET_Y), Point(-SEGMENTS_OFFSET_X * 2, 0)),
    # south_east
    (Point(-SEGMENTS_OFFSET_X * 2, 0), Point(-SEGMENTS_OFFSET_X, -SEGMENTS_OFFSET_Y)),
    # south
    (Point(-SEGMENTS_OFFSET_X, -SEGMENTS_OFFSET_Y), Point(SEGMENTS_OFFSET_X, -SEGMENTS_OFFSET_Y)),
    # south_west
    (Point(SEGMENTS_OFFSET_X, -SEGMENTS_OFFSET_Y), Point(SEGMENTS_OFFSET_X * 2, 0)),
    # north_west
    (Point(SEGMENTS_OFFSET_X * 2, 0), Point(SEGMENTS_OFFSET_X, SEGMENTS_OFFSET_Y)),
)


DIRECTION_DIFFERENCES = (
    # even cols
    [Tile(0, -1), Tile(1, -1), Tile(1, 0), Tile(0, 1), Tile(-1, 0), Tile(-1, -1)],
    # odd cols
    [Tile(0, -1), Tile(1, 0), Tile(1, 1), Tile(0, 1), Tile(-1, 1), Tile(-1, 0)],
)


RenderedMap: TypeAlias = npt.NDArray[np.uint8]
MaybeTile: TypeAlias = Optional[Tile]
Neighbors: TypeAlias = tuple[MaybeTile, MaybeTile, MaybeTile, MaybeTile, MaybeTile, MaybeTile]


@dataclass
class Grid:  # pylint: disable=too-many-instance-attributes
    """Represent a grid of tiles for the game."""

    nb_cols: int
    nb_rows: int
    tiles: tuple[tuple[Tile, ...], ...] = field(
        default_factory=tuple, init=False, repr=False, compare=False, hash=False
    )
    neighbors: dict[Tile, Neighbors] = field(default_factory=dict, init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        """Create the grid."""
        self.tiles = tuple(tuple(Tile(col, row) for col in range(self.nb_cols)) for row in range(self.nb_rows))
        self.tiles_set = set(chain(*self.tiles))
        self.neighbors = {tile: self.compute_neighbors(tile) for tile in self}
        self.first_tile = self.tiles[0][0]
        self.last_tile = self.tiles[-1][-1]
        self.max_distance = self.first_tile.distance(self.last_tile)
        self.max_center_distance = self.first_tile.center_distance(self.last_tile)

    def __iter__(self) -> Iterator[Tile]:
        """Iterate over the tiles."""
        yield from self.tiles_set

    @property
    def nb_tiles(self) -> int:
        """Return the number of tiles."""
        return self.nb_cols * self.nb_rows

    def compute_neighbors(self, tile: Tile) -> Neighbors:
        """Compute the neighbors of a tile."""
        neighbors: list[MaybeTile] = []
        for direction in range(6):
            col_diff, row_diff = DIRECTION_DIFFERENCES[tile.col % 2][direction]
            col = tile.col + col_diff
            row = tile.row + row_diff
            if 0 <= col < self.nb_cols and 0 <= row < self.nb_rows:
                neighbors.append(self.tiles[row][col])
            else:
                neighbors.append(None)
        return neighbors[0], neighbors[1], neighbors[2], neighbors[3], neighbors[4], neighbors[5]  # thanks mypy

    @classmethod
    def compute_grid_size(cls, nb_tiles: int, width_to_height_ratio: float) -> tuple[int, int]:
        # pylint: disable=line-too-long
        """Compute the size of the grid (nb cols, nb_rows) to fit the given number of tiles.

        Parameters
        ----------
        nb_tiles: int
            The approximate number of tiles we want in the grid.
        width_to_height_ratio: float
            The ratio between the height and the width of a tile.
            height = width * width_to_height_ratio

        Returns
        -------
        tuple[int, int]
            The size of the grid (nb cols, nb_rows) to fit the given number of tiles respecting the given ratio.

        Notes
        -----
        Calculus:

        # Assuming the tile size is 1, we have:
        height = (nb_rows * 2 + 1) * HEX_WIDTH_TO_HEIGHT_RATIO
        width = (nb_cols - 1) * 1.5 + 2 = nb_cols * 1.5 + 0.5

        # We also know that:
        nb_cols * nb_rows = nb_tiles
        width * width_to_height_ratio = height

        # So we can reduce:
        (nb_cols * 1.5 + 0.5) * width_to_height_ratio = height
        nb_cols * 1.5 + 0.5 == height / width_to_height_ratio
        nb_cols * 1.5 = height / width_to_height_ratio - 0.5
        nb_cols = (height / width_to_height_ratio - 0.5) / 1.5

        # And we get this first equation:
        nb_cols = (((nb_rows * 2 + 1) * HEX_WIDTH_TO_HEIGHT_RATIO) / width_to_height_ratio - 0.5) / 1.5
        # And this other one from above
        nb_cols = nb_tiles / nb_rows

        # So we can solve for nb_rows:
        (((nb_rows * 2 + 1) * HEX_WIDTH_TO_HEIGHT_RATIO) / width_to_height_ratio - 0.5) / 1.5 = nb_tiles / nb_rows
        ((nb_rows * 2 + 1) * HEX_WIDTH_TO_HEIGHT_RATIO) / width_to_height_ratio - 0.5 = nb_tiles / nb_rows * 1.5
        ((nb_rows * 2 + 1) * HEX_WIDTH_TO_HEIGHT_RATIO) / width_to_height_ratio = nb_tiles / nb_rows * 1.5 + 0.5
        (nb_rows * 2 + 1) * HEX_WIDTH_TO_HEIGHT_RATIO = nb_tiles / nb_rows * 1.5 * width_to_height_ratio + 0.5 * width_to_height_ratio
        nb_rows * 2 + 1 = nb_tiles / nb_rows * 1.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO + 0.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO
        nb_rows² * 2 + 1 = nb_tiles * 1.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO + nb_rows * (0.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO)
        nb_rows² * 2 = nb_tiles * 1.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO + nb_rows * (0.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO) - 1

        # Which give us this second degree equation (ax2 + bx + c = 0):
        nb_rows² * 2 + nb_rows * (-0.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO) + nb_tiles * - 1.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO + 1 = 0

        # Which we can solve with the quadratic formula starting by computing d with:
        a = 2
        b = (-0.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO)
        c = nb_tiles * - 1.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO + 1

        # So we get d:
        d = b² − 4 * a * c

        # We can now get the maximum value of nb_rows:
        nb_rows = (-b + sqrt(d)) / (2 * a)

        # And we deduce the nb of cols:
        nb_cols = nb_tiles / nb_rows

        """
        # pylint: enable=line-too-long
        val_a = 2
        val_b = -0.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO
        val_c = nb_tiles * -1.5 * width_to_height_ratio / HEX_WIDTH_TO_HEIGHT_RATIO + 1
        delta = val_a**2 - 4 * val_a * val_c
        nb_rows = (-val_b + sqrt(delta)) / (2 * val_a)
        nb_cols = nb_tiles / nb_rows
        return floor(nb_cols), floor(nb_rows)

    def tile_distance_from_origin_compensation(self, tile: Tile) -> float:
        """Compute the compensation of a tile depending of its distance from the origin."""
        return tile.center_distance(self.first_tile) / self.max_center_distance * 0.05


TilePoints: TypeAlias = tuple[Point, Point, Point, Point, Point, Point]


class ConcreteTile(NamedTuple):
    """Represent a concrete tile."""

    tile: Tile
    center: Point
    points: TilePoints

    @property
    def col(self) -> int:
        """Return the column of the tile."""
        return self.tile.col

    @property
    def row(self) -> int:
        """Return the row of the tile."""
        return self.tile.row


@dataclass
class ConcreteGrid:  # pylint: disable=too-many-instance-attributes
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
        self.tile_height = self.tile_size * SQRT3
        self.tiles = tuple(
            tuple(
                ConcreteTile(
                    tile,
                    center := self.compute_tile_center(tile),
                    self.compute_tile_points(center),
                )
                for tile in row
            )
            for row in self.grid.tiles
        )
        self.max_coordinates = self.compute_max_coordinates()
        self.map_size = Point(ceil(self.max_coordinates.x + 1), ceil(self.max_coordinates.y + 1))
        self.map = self.create_map()
        self.drawing_map = self.create_map()

    def __iter__(self) -> Iterator[ConcreteTile]:
        """Iterate over the concrete tiles."""
        for row in self.tiles:
            yield from row

    @property
    def nb_rows(self) -> int:
        """Return the number of rows."""
        return self.grid.nb_rows

    @property
    def nb_cols(self) -> int:
        """Return the number of columns."""
        return self.grid.nb_cols

    @property
    def nb_tiles(self) -> int:
        """Return the number of tiles."""
        return self.grid.nb_tiles

    def compute_tile_center(self, tile: Tile) -> Point:
        """Compute the center of a tile.

        Center is moved top/left by half a tile to have the top/left of
        the rectangle containing the Tile(0, 0) to be at (0, 0).
        """
        return Point(
            self.tile_size * 3 / 2 * tile.col + self.tile_width * 1 / 2,
            self.tile_size * SQRT3 * (tile.row + 0.5 * (tile.col % 2)) + self.tile_height * 1 / 2,
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
        return np.zeros((int(self.map_size.y), int(self.map_size.x), 4), dtype=np.uint8)

    def reset_map(self, background: Optional[Color] = None) -> None:
        """Reset the map to 0."""
        if background is None:
            self.map.fill(0)
            self.drawing_map.fill(0)
        else:
            fill = background[::-1] + (255,)
            self.map[:] = fill
            self.drawing_map[:] = fill

    def draw_areas(
        self,
        tiles: Iterable[Tile],
        color: Color,
        mark: bool = False,
        use_transparency: bool = True,
        thickness: int = THICKNESS,
    ) -> None:
        """Draw the (perimeters of the) areas of the given tiles.

        Parameters
        ----------
        tiles : Iterable[Tile]
            The tiles to draw.
        color : Color
            The color to use.
        mark : bool, optional
            Whether to mark the tiles, by default False.
        use_transparency : bool, optional
            Whether to use transparency, by default True.
        thickness : int, optional
            The thickness of the lines, by default THICKNESS.

        """
        if not tiles:
            return

        drawing_color: tuple[int, ...]
        if use_transparency:
            self.drawing_map.fill(0)
            drawing_map = self.drawing_map
            drawing_color = (0, 0, 0, 255)
        else:
            drawing_map = self.map
            drawing_color = color

        tiles_set = set(tiles)
        for tile in tiles_set:
            concrete_tile = self.tiles[tile.row][tile.col]
            if mark:
                cv2.circle(  # pylint: disable=no-member
                    drawing_map,
                    round(concrete_tile.center),  # type: ignore[call-overload]
                    SEGMENTS_OFFSET,
                    drawing_color,
                    thickness,
                    cv2.LINE_AA,  # pylint: disable=no-member
                )
            for direction, neighbor in enumerate(self.grid.neighbors[tile]):
                if neighbor and neighbor in tiles_set:
                    continue
                offsets = SEGMENTS_OFFSETS[direction]
                cv2.line(  # pylint: disable=no-member
                    drawing_map,
                    round(offsets[0] + concrete_tile.points[(direction - 1) % 6]),  # type: ignore[call-overload]
                    round(offsets[1] + concrete_tile.points[direction]),  # type: ignore[call-overload]
                    drawing_color,
                    thickness,
                    cv2.LINE_AA,  # pylint: disable=no-member
                )

        if use_transparency:
            # we set the same color
            mask = np.where(self.drawing_map[:, :, 3] != 0)
            # sadly we cannot do things like self.drawing_map[mask][:,:3] = color
            # self.drawing_map[:, :, 3] = self.drawing_map[:, :, 3] // 2 + 128  # reduce transparency when we have tiles
            self.drawing_map[:, :, :3] = color
            # we update the map with only the pixels that are not fully transparent, i.e. where the tiles are drawn
            self.map[mask] = self.drawing_map[mask]

    def map_as_base64_png(self) -> str:
        """Return the map as an image encoded in base64."""
        array = cv2.imencode(".png", self.map)[1]  # pylint: disable=no-member
        return base64.b64encode(array.tobytes()).decode()

    @classmethod
    def compute_tile_size(cls, nb_cols: int, nb_rows: int, width: int, height: int) -> float:
        """Compute the size of a tile to fit the given number of tiles in the given area.

        Parameters
        ----------
        nb_cols: int
            The number of columns in the grid.
        nb_rows: int
            The number of rows in the grid.
        width: int
            The width of the area.
        height: int
            The height of the area.

        Returns
        -------
        float
            The size of a tile.

        """
        return min(width / (nb_cols * 1.5 + 0.5), height / (nb_rows * SQRT3 + 1))

    @classmethod
    def compute_grid_size(cls, nb_tiles: int, width: int, height: int) -> tuple[int, int, float]:
        """Compute the size of the grid (nb cols, rows, tile size) to fit the given number of tiles in the given area.

        Parameters
        ----------
        nb_tiles: int
            The approximate number of tiles we want in the grid.
        width: int
            The width of the area.
        height: int
            The height of the area.

        """
        nb_cols, nb_rows = Grid.compute_grid_size(nb_tiles, height / width)
        tile_size = cls.compute_tile_size(nb_cols, nb_rows, width, height)
        return nb_cols, nb_rows, tile_size

    def get_tile_at_point(self, point: Point) -> Optional[Tile]:
        """Return the tile at the given point, or None if there is no tile at this position."""
        # computation is done assuming that the coordinate (0, 0) is at the center of the tile (0, 0)
        adjusted_point = Point(point.x - self.tile_width / 2, point.y - self.tile_height / 2)

        tile = (
            AxialCoordinate(
                q=(2.0 / 3 * adjusted_point.x) / self.tile_size,
                r=(-1.0 / 3 * adjusted_point.x + SQRT3 / 3 * adjusted_point.y) / self.tile_size,
            )
            .round()
            .to_tile()
        )
        if 0 <= tile.row < self.grid.nb_rows and 0 <= tile.col < self.grid.nb_cols:
            return tile
        return None

    def draw_map_contour(self, color: Color) -> None:
        """Draw the contour of the map."""
        self.draw_areas(self.grid, color)

    def example_draw_one_map_by_color(self) -> None:
        """Draw one map by color."""
        grid_array = np.array(self.grid.tiles)
        nb_blocks = len(PALETTE_BGR)
        nb_hor_blocks = math.ceil(math.sqrt(nb_blocks))
        nb_ver_blocks = math.ceil(nb_blocks / nb_hor_blocks)
        block_height = math.ceil(self.nb_rows / nb_ver_blocks)
        block_width = math.ceil(self.nb_cols / nb_hor_blocks)
        color_index = 0
        for start_row in range(0, grid_array.shape[0], block_height):
            for start_col in range(0, grid_array.shape[1], block_width):
                block = grid_array[start_row : start_row + block_height, start_col : start_col + block_width]
                self.draw_areas(
                    (Tile(col, row) for col, row in block.reshape(block.shape[0] * block.shape[1], 2)),
                    PALETTE_BGR[color_index % nb_blocks],
                )
                color_index += 1
