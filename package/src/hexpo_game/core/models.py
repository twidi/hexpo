"""Models for the hexpo_game.core app."""

from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone

from .constants import NB_COLORS, ActionType, GameMode, RandomEventTurnMoment
from .grid import Grid
from .types import Tile


class Game(models.Model):
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


class Player(models.Model):
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


class PlayerInGame(models.Model):
    """Represent a player in a game.

    We can have many PlayerInGame for the same (player, game) couple, but only with is_alive = True.
    """

    player = models.ForeignKey(Player, on_delete=models.CASCADE, help_text="Player in the game.")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the player is in.")
    started_turn = models.PositiveIntegerField(help_text="Turn number when the player started.")
    ended_turn = models.PositiveIntegerField(null=True, blank=True, help_text="Turn number when the player ended.")
    color = models.CharField(max_length=7, help_text="Color of the player.")
    start_tile_col = models.IntegerField(
        help_text="The grid column of the start tile in the offset `odd-q` coordinate system."
    )
    start_tile_row = models.IntegerField(
        help_text="The grid row of the start tile in the offset `odd-q` coordinate system."
    )
    level = models.PositiveIntegerField(default=1, help_text="Current level of the player.")
    coins = models.PositiveIntegerField(default=0, help_text="Current number of coins of the player.")
    is_alive = models.BooleanField(default=True, help_text="Whether the player is alive or not.")


class OccupiedTile(models.Model):
    """Represent a tile that is occupied by a player."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the tile is in.")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, help_text="Player that occupies the tile.")
    col = models.IntegerField(help_text="The grid column of the tile in the offset `odd-q` coordinate system.")
    row = models.IntegerField(help_text="The grid row of the tile in the offset `odd-q` coordinate system.")
    level = models.PositiveSmallIntegerField(
        default=20, help_text="Current level of the tile. Max 100. Destroyed at 0."
    )
    updated_at = models.DateTimeField(auto_now=True, help_text="When the tile was last updated.")

    @classmethod
    def has_tiles(cls, game_id: int, player_id: int) -> bool:
        """Return whether the player has tiles or not."""
        return cls.objects.filter(game_id=game_id, player_id=player_id).exists()

    @classmethod
    def has_occupied_neighbors(cls, game_id: int, player_id: int, tile: Tile, grid: Grid) -> bool:
        """Check if the tile has at least one neighbor that is occupied by the player."""
        neighbors: tuple[Tile, ...] = tuple(neighbor for neighbor in grid.neighbors[tile] if neighbor)
        neighbor_filter = Q(col=neighbors[0].col, row=neighbors[0].row)
        for neighbor in neighbors[1:]:
            neighbor_filter |= Q(col=neighbor.col, row=neighbor.row)
        return cls.objects.filter(game_id=game_id, player_id=player_id).filter(neighbor_filter).exists()


class Drop(models.Model):
    """Represent a drop not yet picked up by a player."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the drop is in.")
    tile_col = models.IntegerField(help_text="The grid column of the drop in the offset `odd-q` coordinate system.")
    tile_row = models.IntegerField(help_text="The grid row of the drop in the offset `odd-q` coordinate system.")
    coins = models.PositiveIntegerField(help_text="Number of coins in the drop.")


class Action(models.Model):
    """Represent an action done by a player."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, help_text="Player that did the action.")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, help_text="Game the action is in.")
    turn = models.PositiveIntegerField(help_text="Turn number when the action was done.")
    action_type = models.CharField(max_length=255, help_text="Type of the action.", choices=ActionType.choices)
    tile_col = models.IntegerField(
        help_text="The grid column of the action in the offset `odd-q` coordinate system.", null=True
    )
    tile_row = models.IntegerField(
        help_text="The grid row of the action in the offset `odd-q` coordinate system.", null=True
    )
    confirmed_at = models.DateTimeField(help_text="When the action was confirmed.", null=True)
    efficiency = models.FloatField(help_text="Efficiency of the action. (between 0 and 1)", default=1.0)


class RandomEvent(models.Model):
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
    confirmed_at = models.DateTimeField(help_text="When the event was confirmed.", null=True)
    lightning_damage = models.PositiveIntegerField(help_text="Damage of the lightning.", null=True)
    earthquake_damage = models.PositiveIntegerField(help_text="Damage of the earthquake.", null=True)
    earthquake_radius = models.PositiveIntegerField(help_text="Radius of the earthquake.", null=True)
    drop_coins_amount = models.PositiveIntegerField(help_text="Amount of coins in the drop.", null=True)
