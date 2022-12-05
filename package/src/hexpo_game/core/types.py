"""Simple types for the hexpo_game.core app."""

from __future__ import annotations

import enum
from asyncio import Queue
from random import randint
from textwrap import wrap
from typing import Any, NamedTuple, Optional, TypeAlias, cast


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

    def __round__(self, ndigits: Optional[int] = None) -> Point:
        """Round the point to the nearest integer."""
        return Point(round(self.x, ndigits), round(self.y, ndigits))

    def __mul__(self, other: Any) -> Point:
        """Multiply a point by a value.

        Parameters
        ----------
        other : Any
            - Can be a number, the values of the point will be multiplied by the number.
            - Any other kind of value will raise a TypeError.

        """
        if isinstance(other, (float, int)):
            return Point(self.x * other, self.y * other)
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

    @classmethod
    def random(cls) -> Color:
        """Create a random color."""
        return Color(randint(0, 255), randint(0, 255), randint(0, 255))


TileDistanceCache: dict[tuple[Tile, Tile], int] = {}


class Tile(NamedTuple):
    """Represent a tile."""

    col: int
    row: int

    def to_axial(self) -> AxialCoordinate:
        """Convert to axial coordinate."""
        return AxialCoordinate(self.col, self.row - (self.col - (self.col % 2)) // 2)

    def distance(self, other: Tile) -> int:
        """Return the distance between two tiles."""
        ordered_tiles = cast(tuple[Tile, Tile], tuple(sorted((self, other))))
        if ordered_tiles not in TileDistanceCache:
            TileDistanceCache[ordered_tiles] = self.to_axial().distance(other.to_axial())
        return TileDistanceCache[ordered_tiles]


class AxialCoordinate(NamedTuple):
    """Tile coordinate in the axial coordinate space."""

    q: float
    r: float

    def to_cubic(self) -> CubicCoordinate:
        """Convert to cubic coordinate."""
        return CubicCoordinate(q=self.q, r=self.r, s=-self.q - self.r)

    def to_tile(self) -> Tile:
        """Convert to tile."""
        return Tile(col=round(self.q), row=round(self.r + (self.q - (self.q % 2)) / 2))

    def round(self) -> AxialCoordinate:
        """Round the axial coordinate to the nearest integer one."""
        return self.to_cubic().round().to_axial()

    def __sub__(self, other: AxialCoordinate) -> AxialCoordinate:
        """Subtract two axial coordinates."""
        if isinstance(other, AxialCoordinate):
            return AxialCoordinate(self.q - other.q, self.r - other.r)
        return NotImplemented  # type: ignore[unreachable]

    def distance(self, other: AxialCoordinate) -> int:
        """Return the distance between two axial coordinates."""
        diff = self - other
        return int((abs(diff.q) + abs(diff.r) + abs(diff.q + diff.r)) // 2)


class CubicCoordinate(NamedTuple):
    """Tile coordinate in the cubic coordinate space."""

    q: float
    r: float
    s: float

    def to_axial(self) -> AxialCoordinate:
        """Convert to axial coordinate."""
        return AxialCoordinate(q=self.q, r=self.r)

    def round(self) -> CubicCoordinate:
        """Round the cubic coordinate to the nearest integer one."""
        # pylint: disable=invalid-name
        q = round(self.q)
        r = round(self.r)
        s = round(self.s)
        q_diff = abs(q - self.q)
        r_diff = abs(r - self.r)
        s_diff = abs(s - self.s)
        if q_diff > r_diff and q_diff > s_diff:
            q = -r - s
        elif r_diff > s_diff:
            r = -q - s
        else:
            s = -q - r
        return CubicCoordinate(q=q, r=r, s=s)


class GameMessageKind(enum.Enum):
    """Kind of message."""

    SPAWN = "spawn"
    SPAWN_FAILED = "spawn_failed"
    DEATH = "death"
    OTHER = "other"


class GameMessage(NamedTuple):
    """Message to display."""

    text: str
    kind: GameMessageKind
    color: Optional[Color] = None
    chat_text: Optional[str] = None
    player_id: Optional[int] = None


GameMessages: TypeAlias = list[GameMessage]
GameMessagesQueue: TypeAlias = Queue[GameMessage]
