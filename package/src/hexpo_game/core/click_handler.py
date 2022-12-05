"""Handle confirmed click from viewers."""

from typing import Optional

from .constants import ClickTarget
from .types import Point

SCREEN_SIZE = (2560, 1440)
COORDINATES: dict[ClickTarget, tuple[tuple[int, int], tuple[int, int]]] = {  # ((left, top), (right, bottom))
    ClickTarget.BTN_ATTACK: ((10, 192), (92, 232)),
    ClickTarget.BTN_DEFEND: ((102, 192), (184, 232)),
    ClickTarget.BTN_GROW: ((194, 192), (276, 232)),
    ClickTarget.BTN_BANK: ((286, 192), (368, 232)),
    ClickTarget.MAP: ((464, 232), (2276, 1263)),
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
