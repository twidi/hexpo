"""Constants for the game."""

from django.db import models


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
