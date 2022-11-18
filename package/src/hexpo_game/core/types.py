"""Simple types for the hexpo_game.core app."""

from __future__ import annotations

from random import randint
from textwrap import wrap
from typing import Any, NamedTuple


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

    @classmethod
    def random(cls) -> Color:
        """Create a random color."""
        return Color(randint(0, 255), randint(0, 255), randint(0, 255))


class Tile(NamedTuple):
    """Represent a tile."""

    col: int
    row: int
