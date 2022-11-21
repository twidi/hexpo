"""Constants for the game."""
from datetime import timedelta

from django.db import models

from .types import Color

RESPAWN_WAIT_DURATION = timedelta(seconds=10)


class GameMode(models.TextChoices):
    """The mode of the game."""

    FREE_FULL = "free-full", "Free full"
    FREE_NEIGHBOR = "free-neighbor", "Free neighbor"
    TURN_BY_TURN = "turn-by-turn", "Turn by turn"


class ActionType(models.TextChoices):
    """Represent the different types of actions."""

    ATTACK = "attack", "Attack"
    DEFEND = "defend", "Defend"
    GROW = "grow", "Grow"
    BANK = "bank", "Bank"


class RandomEventType(models.TextChoices):
    """Represent the different types of random events."""

    LIGHTNING = "lightning", "Lightning"
    EARTHQUAKE = "earthquake", "Earthquake"
    DROP_COINS = "drop_coins", "Drop coins"


LIGHTNING_DAMAGES_RANGE = (10, 50)  # Damage to the hit tile
EARTHQUAKE_RADIUS_RANGE = (3, 10)  # Radius of the earthquake
EARTHQUAKE_DAMAGES_RANGE = (10, 50)  # Damage to all tile in the earthquake radius
DROP_COINS_RANGE = (100, 1000)  # Number of coins in the drop
MIN_START_DISTANCE_FROM_DROPS = 3  # Minimum distance between the start tile and the drops


class RandomEventTurnMoment(models.TextChoices):
    """Represent the different moments of the turn where a random event can happen."""

    BEFORE = "before", "Before executions of actions"
    AFTER = "after", "After executions of actions"


# this palette was generated glasbey (using the command next line), removing the first one, white
# ./glasbey.py --no-black --lightness-range 30,70 --view --format byte 21 testpalette
# https://github.com/taketwo/glasbey/ (cannot be installed via pypi)
PALETTE = [
    Color(178, 0, 0),
    Color(0, 140, 0),
    Color(187, 78, 255),
    Color(0, 173, 200),
    Color(236, 156, 0),
    Color(100, 92, 94),
    Color(255, 115, 156),
    Color(10, 225, 145),
    Color(166, 1, 124),
    Color(173, 165, 159),
    Color(175, 178, 255),
    Color(139, 106, 0),
    Color(0, 124, 106),
    Color(174, 206, 0),
    Color(255, 82, 12),
    Color(247, 149, 255),
    Color(176, 99, 88),
    Color(244, 0, 213),
    Color(156, 119, 158),
    Color(135, 160, 86),
]
NB_COLORS = len(PALETTE)

PALETTE_BGR = [color.as_bgr() for color in PALETTE]
