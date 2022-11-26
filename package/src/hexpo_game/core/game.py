"""Main game loop and functions."""
import asyncio
import logging
from asyncio import Queue
from datetime import datetime
from typing import Optional, TypeAlias, cast

from asgiref.sync import sync_to_async
from django.utils import timezone

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .click_handler import COORDINATES, get_click_target
from .constants import NB_COLORS, PALETTE, ActionFailureReason, ActionState, ActionType
from .grid import ConcreteGrid, Grid
from .models import Action, Game, OccupiedTile, Player, PlayerInGame
from .types import Point, Tile

logger = logging.getLogger("hexpo_game.game")
logger_save_action = logging.getLogger("hexpo_game.game.save_action")
logger_play_turn = logging.getLogger("hexpo_game.game.play_turn")


GameQueue: TypeAlias = Queue[tuple[Player, Optional[Tile]]]


async def dequeue_clicks(queue: GameQueue, game: Game, grid: Grid) -> None:
    """Dequeue clicks and process them."""
    now: datetime
    next_turn_min_at = game.current_turn_started_at + game.config.turn_duration
    while True:
        if (now := timezone.now()) >= next_turn_min_at:
            await game.anext_turn(now)
            next_turn_min_at = game.current_turn_started_at + game.config.turn_duration
            await aplay_turn(game, grid, turn=game.current_turn - 1)
        try:
            player, tile = await asyncio.wait_for(queue.get(), timeout=1)
        except asyncio.TimeoutError:
            continue
        else:
            try:
                await asave_action(player, game, tile)
            except Exception:  # pylint:disable=broad-except
                logger.exception("Error while processing click for %s", player.name)
            queue.task_done()


def play_turn(game: Game, grid: Grid, turn: Optional[int] = None) -> None:
    """Play a turn."""
    turn = game.current_turn if turn is None else turn
    queryset = Action.objects.filter(game=game, state=ActionState.CONFIRMED, turn=turn)
    logger_play_turn.info("Playing turn %s: %s actions", turn, len(queryset))
    dead_during_turn: set[int] = set()  # id of dead player in games
    for action in queryset.order_by("confirmed_at").select_related("player_in_game__player"):
        if action.tile_col is None or action.tile_row is None:
            continue
        player_in_game = action.player_in_game
        player = player_in_game.player

        if player_in_game.id in dead_during_turn:
            action.fail(reason=ActionFailureReason.DEAD)
            logger_play_turn.warning("%s IS DEAD (killed in this turn)", player.name)
            continue

        tile = Tile(action.tile_col, action.tile_row)
        occupied_tile = (
            OccupiedTile.objects.filter(game=game, col=tile.col, row=tile.row)
            .select_related("player_in_game__player")
            .first()
        )
        if occupied_tile is not None:
            if occupied_tile.player_in_game.player_id == player.id:
                logger_play_turn.warning("%s clicked on %s but it's already his tile", player.name, tile)
                action.fail(reason=ActionFailureReason.GROW_SELF)
                continue

            if occupied_tile.player_in_game.is_protected():
                logger_play_turn.warning(
                    "%s clicked on %s but is occupied by %s and protected",
                    player.name,
                    tile,
                    occupied_tile.player_in_game.player.name,
                )
                action.fail(reason=ActionFailureReason.GROW_PROTECTED)
                continue

        if (
            game.config.neighbors_only
            and player_in_game.has_tiles()
            and not OccupiedTile.has_occupied_neighbors(player_in_game.id, tile, grid)
        ):
            logger_play_turn.warning("%s clicked on %s but has no neighbors", player.name, tile)
            action.fail(reason=ActionFailureReason.GROW_NO_NEIGHBOR)
            continue

        if occupied_tile is not None:
            old_player_in_game = occupied_tile.player_in_game
            logger_play_turn.info(
                "%s clicked on %s that was occupied by %s", player.name, tile, old_player_in_game.player.name
            )
            occupied_tile.player_in_game = player_in_game
            occupied_tile.save()

            if not old_player_in_game.has_tiles():
                logger_play_turn.warning("%s IS NOW DEAD", old_player_in_game.player.name)
                old_player_in_game.die(turn=turn, killer=player_in_game)
                dead_during_turn.add(old_player_in_game.id)
        else:
            logger_play_turn.info("%s clicked on %s that was not occupied", player.name, tile)
            OccupiedTile.objects.create(game=game, col=tile.col, row=tile.row, player_in_game=player_in_game)

        action.success()


async def aplay_turn(game: Game, grid: Grid, turn: Optional[int] = None) -> None:
    """Play a turn."""
    await sync_to_async(play_turn)(game, grid, turn)


def save_action(player: Player, game: Game, tile: Optional[Tile]) -> Optional[Action]:
    """Save the player action if they clicked one a tile."""
    if tile is None:
        return None

    default_player_attrs = dict(  # noqa: C408
        started_turn=game.current_turn,
        start_tile_col=tile.col,
        start_tile_row=tile.row,
        color=PALETTE[player.id % NB_COLORS].as_hex,
        level=game.config.player_start_level,
    )

    player_in_game = (
        game.playeringame_set.filter(
            player=player,
        )
        .order_by("-id")
        .first()
    )

    if player_in_game is None:
        player_in_game = PlayerInGame.objects.create(
            player=player,
            game=game,
            **default_player_attrs,
        )
        logger_save_action.warning("%s clicked on %s AND IS A NEW PLAYER", player.name, tile)
    elif player_in_game.ended_turn is not None:
        if not player_in_game.can_respawn():
            logger_save_action.warning("%s clicked on %s but IS STILL DEAD", player.name, tile)
            return None

        player_in_game = PlayerInGame.objects.create(
            player=player,
            game=game,
            **default_player_attrs,
        )
        logger_save_action.warning("%s clicked on %s AND IS ALIVE AGAIN", player.name, tile)
    elif player_in_game.get_available_actions() <= 0:
        logger_save_action.warning("%s clicked on %s BUT HAS NOT ACTIONS LEFT", player.name, tile)
        return None
    else:
        logger_save_action.info("%s clicked on %s", player.name, tile)

    return Action.objects.create(
        game=game,
        player_in_game=player_in_game,
        turn=game.current_turn,
        action_type=ActionType.GROW,
        tile_col=tile.col,
        tile_row=tile.row,
        confirmed_at=timezone.now(),
        state=ActionState.CONFIRMED,
    )


async def asave_action(player: Player, game: Game, tile: Optional[Tile]) -> Optional[Action]:
    """Save the player action if they clicked one a tile."""
    return cast(Optional[Action], await sync_to_async(save_action)(player, game, tile))


async def on_click(  # pylint: disable=unused-argument
    player: Player, x_relative: float, y_relative: float, game: Game, grid: ConcreteGrid, queue: GameQueue
) -> None:
    """Display a message when a click is received."""
    target, point = get_click_target(x_relative, y_relative)
    if target == "grid-area":
        area = COORDINATES["grid-area"]
        tile = grid.get_tile_at_point(Point(x=point.x - area[0][0], y=point.y - area[0][1]))

        await queue.put((player, tile))
        if tile is not None:
            return

    logger.info("%s clicked on %s (%s)", player.name, target, point)


def get_game_and_grid() -> tuple[Game, ConcreteGrid]:
    """Get the current game."""
    area = COORDINATES["grid-area"]
    width = area[1][0] - area[0][0]
    height = area[1][1] - area[0][1]
    nb_cols, nb_rows, tile_size = ConcreteGrid.compute_grid_size(500, width, height)
    game = Game.get_current(nb_cols=nb_cols, nb_rows=nb_rows)
    grid = ConcreteGrid(Grid(nb_cols, nb_rows), tile_size)
    return game, grid
