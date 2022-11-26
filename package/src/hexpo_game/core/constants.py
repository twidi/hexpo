"""Constants for the game."""
from datetime import timedelta
from typing import NamedTuple

from django.db import models

from .types import Color

RESPAWN_PROTECTED_DURATION = timedelta(seconds=30)


class GameMode(models.TextChoices):
    """The mode of the game."""

    FREE_FULL = "free-full", "Free full"
    FREE_NEIGHBOR = "free-neighbor", "Free neighbor"
    TURN_BY_TURN = "turn-by-turn", "Turn by turn"


class GameModeConfig(NamedTuple):
    """The configuration of a game mode."""

    neighbors_only: bool
    turn_duration: timedelta
    player_start_level: int
    respawn_cooldown_turns: int
    respawn_cooldown_max_duration: timedelta | None
    respawn_protected_max_turns: int
    respawn_protected_max_tiles: int
    respawn_protected_max_duration: timedelta | None


GAME_MODE_CONFIGS: dict[GameMode, GameModeConfig] = {
    GameMode.FREE_FULL: GameModeConfig(
        neighbors_only=False,
        turn_duration=timedelta(seconds=1),
        player_start_level=3,
        respawn_cooldown_turns=10,
        respawn_cooldown_max_duration=timedelta(seconds=10),
        respawn_protected_max_turns=30,
        respawn_protected_max_tiles=10,
        respawn_protected_max_duration=timedelta(seconds=30),
    ),
    GameMode.FREE_NEIGHBOR: GameModeConfig(
        neighbors_only=True,
        turn_duration=timedelta(seconds=1),
        player_start_level=3,
        respawn_cooldown_turns=10,
        respawn_cooldown_max_duration=timedelta(seconds=10),
        respawn_protected_max_turns=30,
        respawn_protected_max_tiles=10,
        respawn_protected_max_duration=timedelta(seconds=30),
    ),
    GameMode.TURN_BY_TURN: GameModeConfig(
        neighbors_only=True,
        turn_duration=timedelta(minutes=5),
        player_start_level=1,
        respawn_cooldown_turns=5,
        respawn_cooldown_max_duration=None,
        respawn_protected_max_turns=10,
        respawn_protected_max_tiles=10,
        respawn_protected_max_duration=None,
    ),
}


class ActionType(models.TextChoices):
    """Represent the different types of actions."""

    ATTACK = "attack", "Attack"
    DEFEND = "defend", "Defend"
    GROW = "grow", "Grow"
    BANK = "bank", "Bank"


class ActionState(models.TextChoices):
    """Represent the different states of actions."""

    CREATED = "created", "Created"
    CONFIRMED = "confirmed", "Confirmed"
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"


class ActionFailureReason(models.TextChoices):
    """Represent the different reasons of action failure."""

    DEAD = "dead", "Dead"
    GROW_SELF = "grow_self", "Already it's tile"
    GROW_PROTECTED = "grow_protected", "Tile is protected"
    GROW_NO_NEIGHBOR = "grow_no_neighbor", "Not on a neighbor"


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
# ./glasbey.py --no-black --lightness-range 50,100 --chroma-range 40,100 --view --format byte 21 testpalette
# https://github.com/taketwo/glasbey/ (cannot be installed via pypi)
PALETTE = [
    Color(223, 12, 6),
    Color(0, 146, 0),
    Color(182, 14, 255),
    Color(183, 255, 0),
    Color(6, 193, 193),
    Color(255, 140, 192),
    Color(255, 159, 8),
    Color(147, 115, 35),
    Color(212, 0, 145),
    Color(202, 181, 255),
    Color(134, 255, 196),
    Color(158, 186, 98),
    Color(255, 234, 136),
    Color(214, 119, 92),
    Color(5, 141, 112),
]
NB_COLORS = len(PALETTE)

PALETTE_BGR = [color.as_bgr() for color in PALETTE]
