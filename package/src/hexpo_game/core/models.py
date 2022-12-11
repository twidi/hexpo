"""Models for the hexpo_game.core app."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import cached_property
from math import floor
from typing import Any, Optional, cast

from asgiref.sync import sync_to_async
from django.db import models
from django.db.models import Count, F, Max, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from .constants import (
    GAME_MODE_CONFIGS,
    NB_COLORS,
    ActionFailureReason,
    ActionState,
    ActionType,
    GameMode,
    GameModeConfig,
    GameStep,
    RandomEventTurnMoment,
)
from .grid import Grid
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
    max_players_allowed = models.PositiveIntegerField(help_text="Maximum number of players allowed.")
    current_turn = models.PositiveIntegerField(default=0, help_text="Current turn number.")
    current_turn_step = models.CharField(
        max_length=255, null=False, choices=GameStep.choices, default=GameStep.WAITING_FOR_PLAYERS
    )
    current_turn_step_started_at = models.DateTimeField(
        auto_now_add=True, help_text="When the current turn step started."
    )
    current_turn_step_end = models.DateTimeField(help_text="When the current turn step ends.")

    @cached_property
    def config(self) -> GameModeConfig:
        """Get the game config."""
        return GAME_MODE_CONFIGS[GameMode(self.mode)]

    def end_game(self) -> None:
        """End the game."""
        self.ended_at = timezone.now()
        self.save(update_fields=["ended_at"])

    @classmethod
    def get_current(
        cls, nb_cols: int, nb_rows: int, max_players_allowed: int = NB_COLORS, turn_duration_minutes: int = 5
    ) -> Game:
        """Get the current game (or create one if no current one).

        Parameters
        ----------
        nb_cols : int
            Number of columns in the grid. Only used if no current game.
        nb_rows : int
            Number of rows in the grid. Only used if no current game.
        max_players_allowed : int, optional
            Maximum number of players allowed, by default 20. Only used if no current game.
        turn_duration_minutes : int, optional
            Duration of a turn, in minutes, by default 5. Only used if no current game.

        """
        game = cls.objects.filter(ended_at=None).order_by("-started_at").first()
        if game is None:
            game = Game.objects.create(
                grid_nb_cols=nb_cols,
                grid_nb_rows=nb_rows,
                max_players_allowed=max_players_allowed,
                current_turn_step_end=timezone.now() + timedelta(minutes=turn_duration_minutes),
            )
        return game

    def next_turn(self, started_at: Optional[datetime] = None) -> int:
        """Go to the next turn."""
        self.current_turn += 1
        self.current_turn_step_started_at = started_at or timezone.now()
        self.save()
        return self.current_turn

    async def anext_turn(self, started_at: Optional[datetime] = None) -> int:
        """Go to the next turn."""
        return cast(int, await sync_to_async(self.next_turn)(started_at))

    def next_step(self) -> GameStep:
        """Go to the next step."""
        self.current_turn_step = GameStep(self.current_turn_step).next()
        if self.current_turn_step.is_first():
            self.next_turn()
        else:
            self.save(update_fields=["current_turn_step"])
        return self.current_turn_step

    async def anext_step(self) -> GameStep:
        """Go to the next step."""
        return cast(GameStep, await sync_to_async(self.next_step)())

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
    def step_time_left(self) -> timedelta:
        """Get the time left for the current step."""
        return self.current_turn_step_end - timezone.now()

    @property
    def step_time_left_for_human(self) -> Optional[str]:  # pylint: disable=too-many-return-statements
        """Get the time left for the current step, in a human-readable format."""
        if (total_seconds := self.step_time_left.total_seconds()) <= 0:
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

    def get_last_tile_update_at(self) -> Optional[datetime]:
        """Get the date of the last updated tile of the game."""
        return cast(
            Optional[datetime],
            (
                OccupiedTile.objects.filter(game=self)
                .exclude(updated_at__isnull=True)
                .aggregate(max_last_updated=Max("updated_at"))["max_last_updated"]
            ),
        )

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
                return
            player_in_game.banked_actions -= used_actions - player_in_game.level
            player_in_game.banked_actions = max(player_in_game.banked_actions, 0)
            player_in_game.save()

    @classmethod
    async def aupdate_all_banked_actions(cls, used_actions_per_player: dict[int, int]) -> None:
        """Update the banked actions of the player."""
        await sync_to_async(cls.update_all_banked_actions)(used_actions_per_player)


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


class Drop(BaseModel):
    """Represent a drop not yet picked up by a player."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the drop is in.")
    tile_col = models.IntegerField(help_text="The grid column of the drop in the offset `odd-q` coordinate system.")
    tile_row = models.IntegerField(help_text="The grid row of the drop in the offset `odd-q` coordinate system.")
    nb_actions = models.FloatField(help_text="Number of action points in the drop.")


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
    turn_moment = models.CharField(
        max_length=255, help_text="Moment of the turn when the event happened.", choices=RandomEventTurnMoment.choices
    )
    event_type = models.CharField(max_length=255, help_text="Type of the event.")
    tile_col = models.IntegerField(
        help_text="The grid column of the event in the offset `odd-q` coordinate system.", null=True
    )
    tile_row = models.IntegerField(
        help_text="The grid row of the event in the offset `odd-q` coordinate system.", null=True
    )
    lightning_damage = models.PositiveIntegerField(help_text="Damage of the lightning.", null=True)
    earthquake_damage = models.PositiveIntegerField(help_text="Damage of the earthquake.", null=True)
    earthquake_radius = models.PositiveIntegerField(help_text="Radius of the earthquake.", null=True)
    drop_actions_amount = models.FloatField(help_text="Amount of actions points in the drop.", null=True)
