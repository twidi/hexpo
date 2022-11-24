"""Models for the hexpo_game.core app."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional, cast

from asgiref.sync import sync_to_async
from django.db import models
from django.db.models import Count, F, Max, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from .constants import (
    NB_COLORS,
    RESPAWN_PROTECTED_DURATION,
    RESPAWN_PROTECTED_QUANTITY,
    ActionFailureReason,
    ActionState,
    ActionType,
    GameMode,
    RandomEventTurnMoment,
)
from .grid import Grid
from .types import Tile


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
    current_turn_started_at = models.DateTimeField(auto_now_add=True, help_text="When the current turn started.")
    current_turn_end = models.DateTimeField(help_text="When the current turn ends.")

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
                current_turn_end=timezone.now() + timedelta(minutes=turn_duration_minutes),
            )
        return game

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

    def get_players_in_game_with_occupied_tiles(self) -> list[PlayerInGame]:
        """Get the players in game with their occupied tiles prefeteched."""
        return list(self.playeringame_set.filter(dead_at__isnull=True).prefetch_related("occupiedtile_set").all())

    def get_players_in_game_for_leader_board(self, limit: Optional[int] = None) -> QuerySet[PlayerInGame]:
        """Get the players in game for the leader board."""
        queryset = (
            self.get_all_players_in_games()
            .annotate(
                nb_actions=Subquery(
                    Player.objects.filter(id=OuterRef("player_id"))
                    .annotate(count=Count("playeringame__action", filter=Q(playeringame__game_id=self.id)))
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
                nb_tiles=Count("occupiedtile"),
            )
            .select_related("player")
            .order_by("-nb_tiles", "-dead_at")
        )
        if limit is not None:
            queryset = queryset[:limit]
        return queryset


class Player(BaseModel):
    """Represent a player that played at least one game."""

    external_id = models.CharField(
        max_length=255, unique=True, help_text="External ID of the player (like a Twitch id)."
    )
    name = models.CharField(max_length=255, help_text="Name of the player.")
    games = models.ManyToManyField(Game, through="PlayerInGame")
    allowed = models.BooleanField(default=True, help_text="Whether the player is allowed or not.", db_index=True)

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
        help_text="The grid column of the start tile in the offset `odd-q` coordinate system."
    )
    start_tile_row = models.IntegerField(
        help_text="The grid row of the start tile in the offset `odd-q` coordinate system."
    )
    level = models.PositiveIntegerField(default=1, help_text="Current level of the player.")
    banked_actions = models.PositiveIntegerField(
        default=0, help_text="Current number of banked actions points of the player."
    )
    dead_at = models.DateTimeField(null=True, help_text="When the player died. Null if the player is alive.")
    killed_by = models.ForeignKey(
        "self",
        related_query_name="kills",
        related_name="kills",
        null=True,
        on_delete=models.SET_NULL,
        help_text="Who killed the player.",
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
                condition=Q(dead_at__isnull=True),
            ),
        ]

    def has_tiles(self) -> bool:
        """Return whether the player has tiles or not."""
        return self.occupiedtile_set.exists()

    def count_tiles(self) -> int:
        """Return the number of tiles the player has."""
        return self.occupiedtile_set.count()

    def is_protected(self, when: Optional[datetime] = None) -> bool:
        """Return whether the player is protected or not."""
        if when is None:
            when = timezone.now()
        return (
            when < self.started_at + RESPAWN_PROTECTED_DURATION and self.count_tiles() <= RESPAWN_PROTECTED_QUANTITY
        )

    def die(self, turn: Optional[int] = None, killer: Optional[PlayerInGame] = None) -> None:
        """Set the player as dead."""
        self.ended_turn = self.game.current_turn if turn is None else turn
        self.dead_at = timezone.now()
        self.killed_by = killer
        self.save()


class OccupiedTile(BaseModel):
    """Represent a tile that is occupied by a player."""

    player_in_game = models.ForeignKey(
        PlayerInGame, on_delete=models.CASCADE, help_text="Player in game that occupies the tile."
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the tile is in.")
    col = models.IntegerField(help_text="The grid column of the tile in the offset `odd-q` coordinate system.")
    row = models.IntegerField(help_text="The grid row of the tile in the offset `odd-q` coordinate system.")
    level = models.PositiveSmallIntegerField(
        default=20, help_text="Current level of the tile. Max 100. Destroyed at 0."
    )
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
                name="%(app_label)s_%(class)s_game_turn",
                fields=("game", "state", "turn", "confirmed_at"),
            ),
        ]

    def fail(self, reason: ActionFailureReason) -> None:
        """Set the action as failed."""
        self.state = ActionState.FAILURE
        self.failure_reason = reason
        self.save()

    def success(self) -> None:
        """Set the action as successful."""
        self.state = ActionState.SUCCESS
        self.save()


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
