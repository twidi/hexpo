"""Constants for the game."""
from __future__ import annotations

import enum
from datetime import timedelta
from typing import NamedTuple

from django.db import models

from .types import Color

LATENCY_DELAY = timedelta(seconds=10)


class GameMode(models.TextChoices):
    """The mode of the game."""

    FREE_FULL = "free-full", "Free full"
    FREE_NEIGHBOR = "free-neighbor", "Free neighbor"
    TURN_BY_TURN = "turn-by-turn", "Turn by turn"


class GameEndMode(models.TextChoices):
    """The mode of the end of the game."""

    ENDLESS = "endless", "Sans fin"
    TURN_LIMIT = "turn-limit", "Nombre de tours limité"
    FULL_MAP = "full-map", "100% occupation"
    HALF_MAP = "half-map", "50% occupation"


class ActionType(models.TextChoices):
    """Represent the different types of actions."""

    ATTACK = "attack", "Attaquer"
    DEFEND = "defend", "Défendre"
    GROW = "grow", "Conquérir"
    BANK = "bank", "Banquer"
    TILE = "tile", "Case"


class GameModeConfig(NamedTuple):
    """The configuration of a game mode."""

    min_players: int
    max_players: int
    neighbors_only: bool
    step_waiting_for_players_duration: timedelta
    step_collecting_actions_duration: timedelta
    message_delay: timedelta
    default_end_mode: GameEndMode
    multi_steps: bool
    player_start_level: int
    tile_start_level: float
    attack_damage: float
    attack_farthest_efficiency: float
    defend_improvement: float
    bank_value: float
    can_grow_on_occupied: bool
    respawn_cooldown_turns: int
    respawn_cooldown_max_duration: timedelta | None
    respawn_protected_max_turns: int
    respawn_protected_max_tiles: int
    respawn_protected_max_duration: timedelta | None
    player_levels: dict[int, int]

    @property
    def message_delay_ms(self) -> int:
        """Return the delay between messages in milliseconds."""
        return int(self.message_delay.total_seconds() * 1000)

    @property
    def single_step(self) -> bool:
        """Return if the game is in single step mode."""
        return not self.multi_steps


GAME_MODE_CONFIGS: dict[GameMode, GameModeConfig] = {
    GameMode.FREE_FULL: GameModeConfig(
        min_players=1,
        max_players=50,
        neighbors_only=False,
        step_waiting_for_players_duration=timedelta(seconds=0),
        step_collecting_actions_duration=timedelta(seconds=1),
        message_delay=timedelta(seconds=1.25),
        default_end_mode=GameEndMode.ENDLESS,
        multi_steps=False,
        player_start_level=3,
        tile_start_level=100.0,
        attack_damage=0.0,
        attack_farthest_efficiency=0.0,
        defend_improvement=0.0,
        bank_value=0.0,
        can_grow_on_occupied=True,
        respawn_cooldown_turns=10,
        respawn_cooldown_max_duration=timedelta(seconds=10),
        respawn_protected_max_turns=30,
        respawn_protected_max_tiles=10,
        respawn_protected_max_duration=timedelta(seconds=30),
        player_levels={},
    ),
    GameMode.FREE_NEIGHBOR: GameModeConfig(
        min_players=1,
        max_players=50,
        neighbors_only=True,
        step_waiting_for_players_duration=timedelta(seconds=0),
        step_collecting_actions_duration=timedelta(seconds=1),
        message_delay=timedelta(seconds=1.25),
        default_end_mode=GameEndMode.ENDLESS,
        multi_steps=False,
        player_start_level=3,
        tile_start_level=100.0,
        attack_damage=0.0,
        attack_farthest_efficiency=0.0,
        defend_improvement=0.0,
        bank_value=0.0,
        can_grow_on_occupied=True,
        respawn_cooldown_turns=10,
        respawn_cooldown_max_duration=timedelta(seconds=10),
        respawn_protected_max_turns=30,
        respawn_protected_max_tiles=10,
        respawn_protected_max_duration=timedelta(seconds=30),
        player_levels={},
    ),
    GameMode.TURN_BY_TURN: GameModeConfig(
        min_players=2,
        max_players=15,
        neighbors_only=True,
        step_waiting_for_players_duration=timedelta(seconds=10),
        step_collecting_actions_duration=timedelta(seconds=30),
        message_delay=timedelta(seconds=2.5),
        default_end_mode=GameEndMode.HALF_MAP,
        multi_steps=True,
        player_start_level=1,
        tile_start_level=20.0,
        attack_damage=20.0,
        attack_farthest_efficiency=0.25,
        defend_improvement=20.0,
        bank_value=0.8,
        can_grow_on_occupied=False,
        respawn_cooldown_turns=2,
        respawn_cooldown_max_duration=None,
        respawn_protected_max_turns=10,
        respawn_protected_max_tiles=10,
        respawn_protected_max_duration=None,
        player_levels={20: 2, 50: 3, 100: 4, 200: 5, 300: 6, 400: 7},
    ),
}


class ActionState(models.TextChoices):
    """Represent the different states of actions."""

    CREATED = "created", "Created"
    CONFIRMED = "confirmed", "Confirmed"
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"


class ActionFailureReason(models.TextChoices):
    """Represent the different reasons of action failure."""

    DEAD = "dead", "Dead"
    BAD_FIRST = "bad-first", "Bad first"
    GROW_SELF = "grow_self", "Already it's tile"
    GROW_PROTECTED = "grow_protected", "Tile is protected"
    GROW_NO_NEIGHBOR = "grow_no_neighbor", "Not on a neighbor"
    ATTACK_PROTECTED = "attack_protected", "Tile is protected"
    ATTACK_TOO_FAR = "attack_too_far", "Attack too far"
    ATTACK_TOO_MANY = "attack_too_many", "Too many attacks"


class RandomEventType(models.TextChoices):
    """Represent the different types of random events."""

    LIGHTNING = "lightning", "Lightning"
    EARTHQUAKE = "earthquake", "Earthquake"
    DROP_ACTIONS = "drop_actions", "Drop actions"


NO_EVENT_MESSAGES = [
    "Pas de changement notable",
    "Rien de spécial ne s'est produit",
    "Aucune surprise en vue",
    "La vie poursuit son cours sans heurts",
    "Rien de nouveau sous le soleil",
    "R.A.S., tout va bien",
    "C'est trop calme. j'aime pas trop beaucoup ça",
    "J'préfère quand c'est un peu trop plus moins calme",
]

LIGHTNING_DAMAGES_RANGE = (10, 80)  # Damage to the hit tile
EARTHQUAKE_RADIUS_RANGE = (3, 7)  # Radius of the earthquake
EARTHQUAKE_DAMAGES_RANGE = (10, 30)  # Damage to all tile in the earthquake radius
EARTHQUAKE_MIN_DAMAGES = 5  # Damage for tiles the farthest from earthquake center
DROP_ACTIONS_RANGE = (1, 20)  # Number of actions in the drop
RANDOM_EVENTS_PROBABILITIES = {
    RandomEventType.LIGHTNING: (0, 0.15),
    RandomEventType.EARTHQUAKE: (0.2, 0.3),
    RandomEventType.DROP_ACTIONS: (0.3, 0.45),
}
RANDOM_EVENTS_MIN_TURN = 20  # Minimum turn to wait before a random event

NB_ATTACKS_PER_LEVEL = 3  # Number of attacks per level


# Damage to the tile level for each border that is not with a tile from the same player
EROSION_DAMAGES_ACTIVE_PLAYER = 0.1
EROSION_DAMAGES_INACTIVE_PLAYER = 0.25
INACTIVE_PLAYER_THRESHOLD = 10  # Number of turns without action to consider a player inactive


class GameStep(models.TextChoices):
    """Represent the different steps of a game."""

    WAITING_FOR_PLAYERS = "waiting_for_players", "Attente de nouveaux joueurs"
    COLLECTING_ACTIONS = "collecting_actions", "Collecte des actions"
    RANDOM_EVENTS = "random_events", "Évènements aléatoires"
    EXECUTING_ACTIONS = "executing_actions", "Éxécution des actions"
    EROSION = "erosion", "Érosion"

    def next(self) -> GameStep:
        """Return the next step."""
        steps = list(GameStep)
        return steps[(steps.index(self) + 1) % len(steps)]

    def is_first(self) -> bool:
        """Return True if the step is the first one."""
        return self == FirstGameStep


StepChangedDetails: dict[GameStep, str] = {GameStep.COLLECTING_ACTIONS: "Clique sur une case puis confirme"}


FirstGameStep = list(GameStep)[0]


class ClickTarget(str, enum.Enum):
    """Represent the different click targets of the game board."""

    MAP = "grid-area"
    BTN_ATTACK = "action-btn-attack"
    BTN_DEFEND = "action-btn-defend"
    BTN_GROW = "action-btn-grow"
    BTN_BANK = "action-btn-bank"
    BTN_CONFIRM = "action-btn-confirm"


ButtonToAction: dict[ClickTarget, ActionType] = {
    ClickTarget.BTN_BANK: ActionType.BANK,
}


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
