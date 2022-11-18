"""Handle confirmed click from viewers."""

from typing import Optional

from .types import Point

SCREEN_SIZE = (2560, 1440)
COORDINATES: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {  # ((left, top), (right, bottom))
    "action-btn-attack": ((10, 210), (92, 251)),
    "action-btn-defend": ((102, 210), (184, 251)),
    "action-btn-grow": ((194, 210), (276, 251)),
    "action-btn-bank": ((286, 210), (368, 251)),
    "grid-area": ((400, 216), (2176, 1224)),
    # "grid-area": ((400, 216), (1400, 1516)),
}


def get_click_target(x_relative: float, y_relative: float) -> tuple[Optional[str], Point]:
    """Return the target of the click, or None if the click is not on a target.

    Parameters
    ----------
    x_relative: float
        The x coordinate of the click as a number between 0 and 1.
    y_relative: float
        The y coordinate of the click as a number between 0 and 1.

    Returns
    -------
    tuple[Optional[str], Point]
        The target of the click, or None if the click is not on a target, and the coordinates of the click.

    """
    point = Point(int(x_relative * SCREEN_SIZE[0]), int(y_relative * SCREEN_SIZE[1]))

    for target_id, ((left, top), (right, bottom)) in COORDINATES.items():
        if left <= point.x <= right and top <= point.y <= bottom:
            return target_id, point
    return None, point
