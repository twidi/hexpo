"""Handle confirmed click from viewers."""

from typing import Optional

from .constants import ClickTarget
from .types import Point

SCREEN_SIZE = (2560, 1440)
COORDINATES: dict[ClickTarget, tuple[tuple[int, int], tuple[int, int]]] = {  # ((left, top), (right, bottom))
    ClickTarget.BTN_BANK: ((663, 1296), (1132, 1346)),
    ClickTarget.BTN_CONFIRM: ((1601, 1296), (2070, 1346)),
    ClickTarget.MAP: ((464, 232), (2276, 1256)),
}


def get_click_target(x_relative: float, y_relative: float) -> tuple[Optional[ClickTarget], Point]:
    """Return the target of the click, or None if the click is not on a target.

    Parameters
    ----------
    x_relative: float
        The x coordinate of the click as a number between 0 and 1.
    y_relative: float
        The y coordinate of the click as a number between 0 and 1.

    Returns
    -------
    tuple[Optional[ClickTarget], Point]
        The target of the click, or None if the click is not on a target, and the coordinates of the click.

    """
    point = Point(int(x_relative * SCREEN_SIZE[0]), int(y_relative * SCREEN_SIZE[1]))

    for target, ((left, top), (right, bottom)) in COORDINATES.items():
        if left <= point.x <= right and top <= point.y <= bottom:
            return target, point
    return None, point
