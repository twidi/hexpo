"""Models for the hexpo_game.core app."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from functools import cached_property
from math import floor
from random import randint, random
from typing import Any, Optional, cast

from asgiref.sync import sync_to_async
from django.db import models
from django.db.models import Count, F, Max, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from .constants import (
    DROP_ACTIONS_RANGE,
    EARTHQUAKE_DAMAGES_RANGE,
    EARTHQUAKE_MIN_DAMAGES,
    EARTHQUAKE_RADIUS_RANGE,
    GAME_MODE_CONFIGS,
    LIGHTNING_DAMAGES_RANGE,
    RANDOM_EVENTS_PROBABILITIES,
    ActionFailureReason,
    ActionState,
    ActionType,
    GameMode,
    GameModeConfig,
    GameStep,
    RandomEventType,
)
from .grid import ConcreteGrid, Grid
from .types import Color, Tile


class BaseModel(models.Model):
    """Base model for all our models."""

    class Meta:
        """Meta class for BaseModel."""

        abstract = True

    async def arefresh_from_db(self) -> None:
        """Refresh the instance from the database."""
        await sync_to_async(self.refresh_from_db)()

    async def asave(self, *args: Any, **kwargs: Any) -> None:
        """Save the instance."""
        await sync_to_async(self.save)(*args, **kwargs)


class Game(BaseModel):
    """Represent a playing game."""

    mode = models.CharField(max_length=255, choices=GameMode.choices, default=GameMode.FREE_FULL)
    started_at = models.DateTimeField(auto_now_add=True, help_text="When the game started.")
    ended_at = models.DateTimeField(null=True, blank=True, help_text="When the game ended.")
    grid_nb_cols = models.PositiveIntegerField(help_text="Number of columns in the grid.")
    grid_nb_rows = models.PositiveIntegerField(help_text="Number of rows in the grid.")
    current_turn = models.PositiveIntegerField(default=0, help_text="Current turn number.")
    current_turn_step = models.CharField(
        max_length=255, null=False, choices=GameStep.choices, default=GameStep.WAITING_FOR_PLAYERS
    )
    current_turn_step_started_at = models.DateTimeField(null=True, help_text="When the current turn step started.")
    current_turn_step_end = models.DateTimeField(null=True, help_text="When the current turn step ends.")

    force_config: Optional[GameModeConfig] = None

    @cached_property
    def config(self) -> GameModeConfig:
        """Get the game config."""
        if self.force_config is not None:
            return self.force_config
        return GAME_MODE_CONFIGS[GameMode(self.mode)]

    def end_game(self) -> None:
        """End the game."""
        self.ended_at = timezone.now()
        self.save(update_fields=["ended_at"])

    @classmethod
    def get_current(cls, game_mode: GameMode, nb_tiles: int, width: int, height: int) -> tuple[Game, float]:
        """Get the current game (or create one if no current one)."""
        game = cls.objects.filter(mode=game_mode, ended_at=None).order_by("-started_at").first()
        if game is None:
            nb_cols, nb_rows, tile_size = ConcreteGrid.compute_grid_size(nb_tiles, width, height)
            game = Game.objects.create(mode=game_mode, grid_nb_cols=nb_cols, grid_nb_rows=nb_rows)
        else:
            tile_size = ConcreteGrid.compute_tile_size(game.grid_nb_cols, game.grid_nb_rows, width, height)
        return game, tile_size

    def next_turn(self, started_at: Optional[datetime] = None) -> int:
        """Go to the next turn."""
        self.current_turn += 1
        self.current_turn_step_started_at = started_at or timezone.now()
        self.save()
        return self.current_turn

    async def anext_turn(self, started_at: Optional[datetime] = None) -> int:
        """Go to the next turn."""
        return cast(int, await sync_to_async(self.next_turn)(started_at))

    def next_step(self, forced_step: Optional[GameStep] = None) -> GameStep:
        """Go to the next step."""
        if forced_step is not None:
            self.current_turn_step = forced_step
            self.save(update_fields=["current_turn_step"])
        else:
            self.current_turn_step = GameStep(self.current_turn_step).next()
            if self.current_turn_step.is_first():
                self.next_turn()
            else:
                self.save(update_fields=["current_turn_step"])
        return self.current_turn_step

    async def anext_step(self, forced_step: Optional[GameStep] = None) -> GameStep:
        """Go to the next step."""
        return cast(GameStep, await sync_to_async(self.next_step)(forced_step))

    def reset_step_times(self, update_start: bool, duration: timedelta) -> datetime:
        """Reset the step times."""
        now = timezone.now()
        if update_start:
            self.current_turn_step_started_at = now
        self.current_turn_step_end = now + duration
        self.save()
        return self.current_turn_step_end

    async def areset_step_times(self, update_start: bool, duration: timedelta) -> datetime:
        """Reset the step times."""
        return cast(datetime, await sync_to_async(self.reset_step_times)(update_start, duration))

    @property
    def step_time_left_for_human(self) -> Optional[str]:  # pylint: disable=too-many-return-statements
        """Get the time left for the current step, in a human-readable format."""
        if self.current_turn_step_end is None:
            return None
        if (total_seconds := (self.current_turn_step_end - timezone.now()).total_seconds()) <= 0:
            return None
        if total_seconds <= 0.5:
            return "0s"
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = min(59, round(total_seconds % 60))
        if hours:
            if minutes or seconds:
                if seconds:
                    return f"{hours}h {minutes}m {seconds}s"
                return f"{hours}h {minutes}m"
            return f"{hours}h"
        if minutes:
            if seconds:
                return f"{minutes}m {seconds}s"
            return f"{minutes}m"
        return f"{seconds}s"

    def get_all_players_in_games(self) -> QuerySet[PlayerInGame]:
        """Get the players in the game, dead or alive."""
        return self.playeringame_set.alias(
            last_playeringame_id=Subquery(
                PlayerInGame.objects.filter(game_id=self.id, player_id=OuterRef("player_id"))
                .values("player_id")
                .order_by()
                .annotate(last_id=Max("id"))
                .values("last_id"),
                output_fields=models.IntegerField(),
            ),
        ).filter(id=F("last_playeringame_id"))

    def get_current_players_in_game(self) -> QuerySet[PlayerInGame]:
        """Get the players in game."""
        return self.playeringame_set.filter(ended_turn__isnull=True)

    def get_all_players_ids_in_game(self) -> set[int]:
        """Get the ids of the players in game."""
        return set(self.playeringame_set.all().distinct("player_id").values_list("player_id", flat=True))

    def get_current_players_in_game_with_occupied_tiles(self) -> list[PlayerInGame]:
        """Get the players in game with their occupied tiles prefeteched."""
        return list(self.get_current_players_in_game().prefetch_related("occupiedtile_set").all())

    def get_players_in_game_for_leader_board(self, limit: Optional[int] = None) -> QuerySet[PlayerInGame]:
        """Get the players in game for the leader board."""
        queryset = self.get_all_players_in_games().annotate(nb_tiles=Count("occupiedtile"))
        if self.config.multi_steps:
            queryset = queryset.filter(
                Q(ended_turn__isnull=True) | Q(ended_turn__gte=self.current_turn - self.config.respawn_cooldown_turns)
            )
        else:
            queryset = queryset.annotate(
                nb_actions=Subquery(
                    Player.objects.filter(id=OuterRef("player_id"))
                    .annotate(
                        count=Count(
                            "playeringame__action",
                            filter=Q(playeringame__game_id=self.id, playeringame__action__state=ActionState.SUCCESS),
                        )
                    )
                    .values("count")[:1]
                ),
                nb_games=Subquery(
                    Player.objects.filter(id=OuterRef("player_id"))
                    .annotate(count=Count("playeringame", filter=Q(playeringame__game_id=self.id)))
                    .values("count")[:1]
                ),
                nb_kills=Subquery(
                    Player.objects.filter(id=OuterRef("player_id"))
                    .annotate(count=Count("playeringame__kills", filter=Q(playeringame__game_id=self.id)))
                    .values("count")[:1]
                ),
            )
        queryset = queryset.select_related("player").order_by("-nb_tiles", "-dead_at")
        if limit is not None:
            queryset = queryset[:limit]
        return queryset

    def confirmed_actions_for_turn(self, turn: Optional[int] = None) -> QuerySet[Action]:
        """Get the confirmed actions for the given turn."""
        if turn is None:
            turn = self.current_turn
        return self.action_set.filter(state=ActionState.CONFIRMED, turn=turn)

    def is_over(self) -> bool:
        """Check if the game is over."""
        return self.ended_at is not None

    @property
    def step(self) -> GameStep:
        """Get the current step of the game."""
        return GameStep(self.current_turn_step)

    @cached_property
    def grid(self) -> Grid:
        """Get the grid."""
        return Grid(self.grid_nb_cols, self.grid_nb_rows)


class Player(BaseModel):
    """Represent a player that played at least one game."""

    external_id = models.CharField(
        max_length=255, unique=True, help_text="External ID of the player (like a Twitch id)."
    )
    name = models.CharField(max_length=255, help_text="Name of the player.")
    games = models.ManyToManyField(Game, through="PlayerInGame")
    allowed = models.BooleanField(default=True, help_text="Whether the player is allowed or not.", db_index=True)
    welcome_chat_message_sent_at = models.DateTimeField(
        default=None, null=True, help_text="Date of the welcome message."
    )

    def __str__(self) -> str:
        """Return the string representation of the player."""
        return f"User #{self.external_id} ({self.name})"

    @classmethod
    def get_not_allowed_ids(cls) -> set[str]:
        """Return the external IDs of the players that are not allowed.

        Returns
        -------
        set[str]
            The external IDs of the players that are not allowed.

        """
        return set(Player.objects.filter(allowed=False).values_list("external_id", flat=True))


class PlayerInGame(BaseModel):
    """Represent a player in a game.

    We can have many PlayerInGame for the same (player, game) couple, but only with is_alive = True.
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, help_text="Player in the game.")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the player is in.")
    started_at = models.DateTimeField(auto_now_add=True, help_text="When the player joined the game.")
    started_turn = models.PositiveIntegerField(help_text="Turn number when the player started.")
    ended_turn = models.PositiveIntegerField(null=True, blank=True, help_text="Turn number when the player died.")
    color = models.CharField(max_length=7, help_text="Color of the player.")
    start_tile_col = models.IntegerField(
        help_text="The grid column of the start tile in the offset `odd-q` coordinate system.", null=True
    )
    start_tile_row = models.IntegerField(
        help_text="The grid row of the start tile in the offset `odd-q` coordinate system.", null=True
    )
    level = models.PositiveIntegerField(default=1, help_text="Current level of the player.")
    banked_actions = models.FloatField(default=0, help_text="Current number of banked actions points of the player.")
    dead_at = models.DateTimeField(null=True, help_text="When the player died. Null if the player is alive.")
    killed_by = models.ForeignKey(
        "self",
        related_query_name="kills",
        related_name="kills",
        null=True,
        on_delete=models.SET_NULL,
        help_text="Who killed the player.",
    )
    first_in_game_for_player = models.BooleanField(
        default=False, help_text="Whether this is the first appearance of the player in the game."
    )

    class Meta:
        """Meta class for PlayerInGame."""

        constraints = [
            models.UniqueConstraint(
                name="%(app_label)s_%(class)s_game_player_is_alive",
                fields=(
                    "game",
                    "player",
                ),
                condition=Q(ended_turn__isnull=True),
            ),
        ]

    @cached_property
    def color_object(self) -> Color:
        """Get the color object of the player."""
        return Color.from_hex(self.color)

    def has_tiles(self) -> bool:
        """Return whether the player has tiles or not."""
        return self.occupiedtile_set.exists()

    def count_tiles(self, precomputed: Optional[int] = None) -> int:
        """Return the number of tiles the player has."""
        return self.occupiedtile_set.count() if precomputed is None else precomputed

    def is_protected(self, nb_tiles: Optional[int] = None) -> bool:
        """Return whether the player is protected or not."""
        return (
            self.started_turn + self.game.config.respawn_protected_max_turns + 1 > self.game.current_turn
            and self.count_tiles(nb_tiles) <= self.game.config.respawn_protected_max_tiles
            and (
                self.game.config.respawn_protected_max_duration is None
                or self.started_at + self.game.config.respawn_protected_max_duration > timezone.now()
            )
        )

    def can_respawn(self) -> bool:
        """Return whether the player can respawn or not."""
        return (
            self.ended_turn is None
            or self.start_tile_col is None
            or self.ended_turn + self.game.config.respawn_cooldown_turns + 1 <= self.game.current_turn
            or (
                self.dead_at is not None
                and self.game.config.respawn_cooldown_max_duration is not None
                and self.dead_at + self.game.config.respawn_cooldown_max_duration < timezone.now()
            )
        )

    def die(self, turn: Optional[int] = None, killer: Optional[PlayerInGame] = None) -> None:
        """Set the player as dead."""
        self.ended_turn = self.game.current_turn if turn is None else turn
        self.dead_at = timezone.now()
        self.killed_by = killer
        self.save()

    async def adie(self, turn: Optional[int] = None, killer: Optional[PlayerInGame] = None) -> None:
        """Set the player as dead."""
        await sync_to_async(self.die)(turn, killer)

    def get_available_actions(self, nb_actions_in_turn: Optional[int] = None) -> int:
        """Return the number of available actions for the player for the current turn."""
        if nb_actions_in_turn is None:
            nb_actions_in_turn = self.get_nb_actions_in_turn()
        return floor(self.level + self.banked_actions - nb_actions_in_turn)

    def can_create_action(self) -> bool:
        """Return whether the player can create an action or not."""
        return self.get_available_actions() > 0

    def get_nb_actions_in_turn(self) -> int:
        """Return the number of actions the player has done in the current turn."""
        return self.action_set.filter(turn=self.game.current_turn).exclude(state=ActionState.CREATED).count()

    def reset_start_tile(self, col: Optional[int] = None, row: Optional[int] = None) -> None:
        """Reset the start tile of the player."""
        self.start_tile_col = col
        self.start_tile_row = row
        self.save()

    @classmethod
    def update_all_banked_actions(cls, used_actions_per_player: dict[int, int]) -> None:
        """Update the banked actions of the player."""
        players_in_game = PlayerInGame.objects.in_bulk(used_actions_per_player.keys())
        for player_in_game_id, used_actions in used_actions_per_player.items():
            player_in_game = players_in_game[player_in_game_id]
            if used_actions <= player_in_game.level:
                continue
            player_in_game.banked_actions -= used_actions - player_in_game.level
            player_in_game.banked_actions = max(player_in_game.banked_actions, 0)
            player_in_game.save()

    @classmethod
    async def aupdate_all_banked_actions(cls, used_actions_per_player: dict[int, int]) -> None:
        """Update the banked actions of the player."""
        await sync_to_async(cls.update_all_banked_actions)(used_actions_per_player)

    async def compute_level(self, start_level: int, levels: dict[int, int]) -> int:
        """Compute the level of a player in game depending of the number of tiles he has."""
        if not levels:
            return start_level
        player_nb_tiles = getattr(self, "nb_tiles", None)
        if player_nb_tiles is None:
            player_nb_tiles = await self.occupiedtile_set.acount()
        player_level = start_level
        for nb_tiles, level in levels.items():
            if player_nb_tiles >= nb_tiles:
                player_level = level
            else:
                break
        return player_level

    @classmethod
    async def aupdate_all_levels(cls, game: Game) -> dict[PlayerInGame, tuple[int, int]]:
        """Update the level of all players in game."""
        if not game.config.player_levels:
            return {}
        players_in_game = await sync_to_async(
            lambda: list(
                game.get_current_players_in_game().select_related("player").annotate(nb_tiles=Count("occupiedtile"))
            )
        )()
        updated: dict[PlayerInGame, tuple[int, int]] = {}
        for player_in_game in players_in_game:
            new_level = await player_in_game.compute_level(game.config.player_start_level, game.config.player_levels)
            if new_level != player_in_game.level:
                updated[player_in_game] = (player_in_game.level, new_level)
                player_in_game.level = new_level
                await player_in_game.asave()
        return updated


class OccupiedTile(BaseModel):
    """Represent a tile that is occupied by a player."""

    player_in_game = models.ForeignKey(
        PlayerInGame, on_delete=models.CASCADE, help_text="Player in game that occupies the tile."
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the tile is in.")
    col = models.IntegerField(help_text="The grid column of the tile in the offset `odd-q` coordinate system.")
    row = models.IntegerField(help_text="The grid row of the tile in the offset `odd-q` coordinate system.")
    level = models.FloatField(default=20, help_text="Current level of the tile. Max 100. Destroyed at 0.")
    updated_at = models.DateTimeField(auto_now=True, help_text="When the tile was last updated.", db_index=True)

    class Meta:
        """Meta class for OccupiedTile."""

        unique_together = ("game", "col", "row")

    @classmethod
    def has_occupied_neighbors(cls, player_in_game_id: int, tile: Tile, grid: Grid) -> bool:
        """Check if the tile has at least one neighbor that is occupied by the player."""
        neighbors: tuple[Tile, ...] = tuple(neighbor for neighbor in grid.neighbors[tile] if neighbor)
        neighbor_filter = Q(col=neighbors[0].col, row=neighbors[0].row)
        for neighbor in neighbors[1:]:
            neighbor_filter |= Q(col=neighbor.col, row=neighbor.row)
        return cls.objects.filter(player_in_game_id=player_in_game_id).filter(neighbor_filter).exists()

    @cached_property
    def tile(self) -> Tile:
        """Get the tile object."""
        return Tile(self.col, self.row)


class Action(BaseModel):
    """Represent an action done by a player."""

    player_in_game = models.ForeignKey(
        PlayerInGame, on_delete=models.CASCADE, help_text="Player in game that did the action."
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the action was done in.")
    turn = models.PositiveIntegerField(help_text="Turn number when the action was done.")
    action_type = models.CharField(max_length=255, help_text="Type of the action.", choices=ActionType.choices)
    tile_col = models.IntegerField(
        help_text="The grid column of the action in the offset `odd-q` coordinate system.", null=True
    )
    tile_row = models.IntegerField(
        help_text="The grid row of the action in the offset `odd-q` coordinate system.", null=True
    )
    state = models.CharField(
        max_length=255, help_text="State of the action.", choices=ActionState.choices, default=ActionState.CREATED
    )
    failure_reason = models.CharField(
        max_length=255, help_text="Reason of the failure.", choices=ActionFailureReason.choices, null=True
    )
    confirmed_at = models.DateTimeField(help_text="When the action was confirmed.", null=True, db_index=True)
    efficiency = models.FloatField(help_text="Efficiency of the action. (between 0 and 1)", default=1.0)

    class Meta:
        """Meta class for Action."""

        constraints = [
            # when the state is not "CREATED", the `confirmed_at` field must be set
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_confirmed_at_not_null_if_not_created",
                check=Q(state=ActionState.CREATED) | Q(confirmed_at__isnull=False),
            ),
            # when the state is "CREATED", the `confirmed_at` field must be null
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_confirmed_at_null_if_created",
                check=~Q(state=ActionState.CREATED) | Q(confirmed_at__isnull=True),
            ),
            # when the state is "FAILED", the `failure_reason` field must be set
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_failure_reason_not_null_if_failed",
                check=~Q(state=ActionState.FAILURE) | Q(failure_reason__isnull=False),
            ),
        ]

        indexes = [
            models.Index(
                # use to query actions on a turn
                name="%(app_label)s_%(class)s_game_turn",
                fields=("game", "state", "turn", "confirmed_at"),
            ),
            models.Index(
                # used to count valid actions of users in a turn
                name="%(app_label)s_%(class)s_player_turn",
                fields=("player_in_game", "turn", "state"),
                condition=~Q(state=ActionState.CREATED),
            ),
        ]

    def confirm(self, efficiency: float = 1.0) -> None:
        """Confirm the action."""
        self.state = ActionState.CONFIRMED
        self.confirmed_at = timezone.now()
        self.efficiency = efficiency
        self.save()

    def fail(self, reason: ActionFailureReason) -> None:
        """Set the action as failed."""
        self.state = ActionState.FAILURE
        self.failure_reason = reason
        self.save()

    def success(self) -> None:
        """Set the action as successful."""
        self.state = ActionState.SUCCESS
        self.save()

    @property
    def tile(self) -> Optional[Tile]:
        """Get the tile object."""
        if self.tile_col is None or self.tile_row is None:
            return None
        return Tile(self.tile_col, self.tile_row)

    def set_tile(self, tile: Tile | None, save: bool = True) -> None:
        """Set the tile of the action."""
        if self.tile == tile:
            return
        if tile is None:
            self.tile_col = None
            self.tile_row = None
        else:
            self.tile_col = tile.col
            self.tile_row = tile.row
        if save:
            self.save()

    def is_tile_set(self) -> bool:
        """Check if the tile of the action is set."""
        return self.tile_col is not None and self.tile_row is not None

    @property
    def efficiency_for_human(self) -> str:
        """Get the efficiency readable by humans."""
        return f"{round(self.efficiency * 100)}%"

    @property
    def type(self) -> ActionType:
        """Get the type of the action."""
        return ActionType(self.action_type)


class RandomEvent(BaseModel):
    """Represent a random event."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the event is in.")
    turn = models.PositiveIntegerField(help_text="Turn number when the event happened.")
    event_type = models.CharField(max_length=255, help_text="Type of the event.", choices=RandomEventType.choices)
    tile_col = models.IntegerField(help_text="The grid column of the event in the offset `odd-q` coordinate system.")
    tile_row = models.IntegerField(help_text="The grid row of the event in the offset `odd-q` coordinate system.")
    lightning_damage = models.PositiveIntegerField(help_text="Damage of the lightning.", default=0)
    earthquake_damage = models.PositiveIntegerField(help_text="Damage of the earthquake.", default=0)
    earthquake_radius = models.PositiveIntegerField(help_text="Radius of the earthquake.", default=0)
    drop_actions_amount = models.FloatField(help_text="Amount of actions points in the drop.", default=0)
    drop_picked_up = models.BooleanField(help_text="Whether the drop was picked up.", default=False)

    class Meta:
        """Meta class for RandomEvent."""

        indexes = [
            models.Index(
                fields=["game", "tile_col", "tile_row"],
                condition=Q(event_type=RandomEventType.DROP_ACTIONS, drop_picked_up=False),
                name="drop_not_picked_up",
            ),
        ]

    @cached_property
    def tile(self) -> Tile:
        """Get the tile object."""
        return Tile(self.tile_col, self.tile_row)

    @classmethod
    def generate_event(cls, game: Game) -> Optional[RandomEvent]:
        """Generate a random event."""
        threshold = random()
        for kind, (low, high) in RANDOM_EVENTS_PROBABILITIES.items():
            if low <= threshold < high:
                if kind == RandomEventType.DROP_ACTIONS:
                    return cls.create_drop_event(game)
                if kind == RandomEventType.LIGHTNING:
                    return cls.create_lightning_event(game)
                if kind == RandomEventType.EARTHQUAKE:
                    return cls.create_earthquake_event(game)
                break
        return None

    @staticmethod
    def generate_random_value(low: int, high: int) -> int:
        """Generate a random value between `low` and `high`."""
        power_low = round(math.sqrt(low * 100))
        power_high = round(math.sqrt(high * 100))
        return (randint(power_low, power_high) * randint(power_low, power_high)) // 100

    @classmethod
    def get_random_tile(cls, game: Game) -> Tile:
        """Get a random tile in the game."""
        return Tile(randint(0, game.grid_nb_cols - 1), randint(0, game.grid_nb_rows - 1))

    @classmethod
    def create_lightning_event(
        cls, game: Game, tile: Optional[Tile] = None, damage: Optional[int] = None
    ) -> RandomEvent:
        """Create a lightning event."""
        if tile is None:
            tile = cls.get_random_tile(game)
        return cls.objects.create(
            game=game,
            turn=game.current_turn,
            event_type=RandomEventType.LIGHTNING,
            tile_col=tile.col,
            tile_row=tile.row,
            lightning_damage=cls.generate_random_value(*LIGHTNING_DAMAGES_RANGE) if damage is None else damage,
        )

    @classmethod
    def create_earthquake_event(
        cls,
        game: Game,
        tile: Optional[Tile] = None,
        damage: Optional[int] = None,
        radius: Optional[int] = None,
    ) -> RandomEvent:
        """Create an earthquake event."""
        if tile is None:
            tile = cls.get_random_tile(game)
        return cls.objects.create(
            game=game,
            turn=game.current_turn,
            event_type=RandomEventType.EARTHQUAKE,
            tile_col=tile.col,
            tile_row=tile.row,
            earthquake_damage=cls.generate_random_value(*EARTHQUAKE_DAMAGES_RANGE) if damage is None else damage,
            earthquake_radius=cls.generate_random_value(*EARTHQUAKE_RADIUS_RANGE) if radius is None else radius,
        )

    @classmethod
    def create_drop_event(cls, game: Game, tile: Optional[Tile] = None, amount: Optional[int] = None) -> RandomEvent:
        """Create a drop event."""
        if tile is None:
            tile = cls.get_random_tile(game)
        return cls.objects.create(
            game=game,
            turn=game.current_turn,
            event_type=RandomEventType.DROP_ACTIONS,
            tile_col=tile.col,
            tile_row=tile.row,
            drop_actions_amount=cls.generate_random_value(*DROP_ACTIONS_RANGE) if amount is None else amount,
        )

    @classmethod
    def apply_damage_to_tile(cls, occupied_tile: OccupiedTile, damage: float) -> bool:
        """Apply damage to a tile."""
        occupied_tile.level -= damage
        if occupied_tile.level <= 0:
            occupied_tile.delete()
            return True
        occupied_tile.save()
        return False

    def apply_lightning(self) -> tuple[None, None] | tuple[PlayerInGame, bool]:
        """Apply the lightning to the grid."""
        if self.event_type != RandomEventType.LIGHTNING:
            return None, None
        occupied_tile = (
            self.game.occupiedtile_set.filter(col=self.tile_col, row=self.tile_row)
            .select_related("player_in_game__player")
            .first()
        )
        if occupied_tile is None:
            return None, None
        return (
            occupied_tile.player_in_game,
            self.apply_damage_to_tile(occupied_tile, self.lightning_damage),
        )

    def apply_earthquake(self, grid: Grid) -> dict[PlayerInGame, tuple[int, int]]:
        """Apply the earthquake to the grid."""
        if self.event_type != RandomEventType.EARTHQUAKE:
            return {}
        tiles = grid.get_tiles_in_radius(center := self.tile, self.earthquake_radius)
        tiles_filter = Q(col=tiles[0].col, row=tiles[0].row)
        for neighbor in tiles[1:]:
            tiles_filter |= Q(col=neighbor.col, row=neighbor.row)
        occupied_tiles = list(
            self.game.occupiedtile_set.filter(tiles_filter).select_related("player_in_game__player")
        )
        if not occupied_tiles:
            return {}
        damages = {
            distance: (EARTHQUAKE_MIN_DAMAGES - self.earthquake_damage) * distance / (self.earthquake_radius - 1)
            + self.earthquake_damage
            for distance in range(self.earthquake_radius)
        }
        touched_players_in_game: dict[PlayerInGame, tuple[int, int]] = {}
        for occupied_tile in occupied_tiles:
            if occupied_tile.player_in_game not in touched_players_in_game:
                touched_players_in_game[occupied_tile.player_in_game] = (0, 0)
            touched_players_in_game[occupied_tile.player_in_game] = (
                touched_players_in_game[occupied_tile.player_in_game][0] + 1,
                touched_players_in_game[occupied_tile.player_in_game][1]
                + self.apply_damage_to_tile(occupied_tile, damages[center.distance(occupied_tile.tile)]),
            )
        return touched_players_in_game

    def apply_drop(self, occupied_tile: Optional[OccupiedTile] = None) -> Optional[PlayerInGame]:
        """Apply the drop to the grid."""
        if self.event_type != RandomEventType.DROP_ACTIONS:
            return None
        if occupied_tile is None:
            occupied_tile = (
                self.game.occupiedtile_set.filter(col=self.tile_col, row=self.tile_row)
                .select_related("player_in_game__player")
                .first()
            )
        elif occupied_tile.col != self.tile_col or occupied_tile.row != self.tile_row:
            return None
        if occupied_tile is None:
            return None
        self.drop_picked_up = True
        self.save()
        player_in_game = occupied_tile.player_in_game
        player_in_game.banked_actions += self.drop_actions_amount
        player_in_game.save()
        return player_in_game
