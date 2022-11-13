"""Models for the hexpo_game.core app."""

from django.db import models

from hexpo_game.core.constants import ActionType, RandomEventTurnMoment


class Game(models.Model):
    """Represent a playing game."""

    started_at = models.DateTimeField(auto_now_add=True, help_text="When the game started.")
    ended_at = models.DateTimeField(null=True, blank=True, help_text="When the game ended.")
    grid_nb_cols = models.PositiveIntegerField(help_text="Number of columns in the grid.")
    grid_nb_rows = models.PositiveIntegerField(help_text="Number of rows in the grid.")
    max_players_allowed = models.PositiveIntegerField(help_text="Maximum number of players allowed.")
    current_turn = models.PositiveIntegerField(default=0, help_text="Current turn number.")
    current_turn_started_at = models.DateTimeField(help_text="When the current turn started.")
    current_turn_end = models.DateTimeField(help_text="When the current turn ends.")


class Player(models.Model):
    """Represent a player that played at least one game."""

    external_id = models.CharField(
        max_length=255, unique=True, help_text="External ID of the player (like a Twitch id)."
    )
    name = models.CharField(max_length=255, help_text="Name of the player.")
    games = models.ManyToManyField(Game, through="PlayerInGame")


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
