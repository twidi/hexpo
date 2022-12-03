"""Main game loop and functions."""
import asyncio
import logging
from asyncio import Queue
from datetime import datetime
from string import ascii_letters
from typing import Any, Optional, TypeAlias, cast

from asgiref.sync import sync_to_async
from django.utils import timezone

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .click_handler import COORDINATES, get_click_target
from .constants import NB_COLORS, PALETTE, ActionFailureReason, ActionState, ActionType
from .grid import ConcreteGrid, Grid
from .models import Action, Game, OccupiedTile, Player, PlayerInGame
from .twitch import ChatMessagesQueue
from .types import Color, Point, Tile

logger = logging.getLogger("hexpo_game.game")
logger_save_action = logging.getLogger("hexpo_game.game.save_action")
logger_play_turn = logging.getLogger("hexpo_game.game.play_turn")


ClicksQueue: TypeAlias = Queue[tuple[Player, Optional[Tile]]]


def human_coordinates(col: int, row: int) -> str:
    """Get the human coordinates."""
    return f"{ascii_letters[26:][row]}‑{col + 1}"


async def dequeue_clicks(queue: ClicksQueue, game: Game, grid: Grid, chats_messages_queue: ChatMessagesQueue) -> None:
    """Dequeue clicks and process them."""
    now: datetime
    next_turn_min_at = game.current_turn_started_at + game.config.turn_duration
    seen_players_ids: set[int] = await sync_to_async(game.get_all_players_ids_in_game)()
    while True:
        if (now := timezone.now()) >= next_turn_min_at and await game.confirmed_actions_for_turn().aexists():
            await game.anext_turn(now)
            next_turn_min_at = game.current_turn_started_at + game.config.turn_duration
            messages = await aplay_turn(game, grid, seen_players_ids, game.current_turn - 1)
            for message in messages:
                await chats_messages_queue.put(message)
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


def play_turn(  # pylint:disable=too-many-locals,too-many-branches,too-many-statements
    game: Game, grid: Grid, seen_players_ids: set[int], turn: Optional[int] = None
) -> list[str]:
    """Play a turn."""
    turn = game.current_turn if turn is None else turn
    messages = []
    queryset = game.confirmed_actions_for_turn(turn)
    logger_play_turn.info("Playing turn %s: %s actions", turn, len(queryset))
    dead_during_turn: set[int] = set()  # id of dead player in games
    on_protected: set[int] = set()  # id of player that clicked only a protected tile
    seen_in_turn: dict[int, tuple[Player, Tile]] = {}  # id of player: (player, tile)
    for action in queryset.order_by("confirmed_at").select_related("player_in_game__player"):
        if (action.tile_col is None or action.tile_row is None) and action.action_type != ActionType.BANK:
            continue
        player_in_game = action.player_in_game
        player = player_in_game.player

        if player_in_game.id in dead_during_turn:
            action.fail(reason=ActionFailureReason.DEAD)
            logger_play_turn.warning("%s IS DEAD (killed in this turn)", player.name)
            continue

        if action.action_type == ActionType.BANK:
            old_banked = player_in_game.banked_actions
            player_in_game.banked_actions += (banked := game.config.bank_value * action.efficiency)
            player_in_game.save()
            action.success()
            logger_play_turn.info(
                "%s banked %s (from %s to %s)",
                player.name,
                f"{banked:.2f}",
                f"{old_banked:.2f}",
                f"{player_in_game.banked_actions:.2f}",
            )
            continue

        tile = Tile(action.tile_col, action.tile_row)  # type: ignore[arg-type]  # we know we have a tile
        seen_in_turn[player.id] = (player, tile)
        occupied_tile = (
            OccupiedTile.objects.filter(game=game, col=tile.col, row=tile.row)
            .select_related("player_in_game__player")
            .first()
        )

        if action.action_type == ActionType.ATTACK:
            if occupied_tile is None:
                logger_play_turn.warning("%s attacked %s but it's not occupied", player.name, tile)
                action.fail(reason=ActionFailureReason.ATTACK_EMPTY)
                continue

            current_player_in_game = occupied_tile.player_in_game
            current_player_name = (
                current_player_in_game.player.name if current_player_in_game.player_id != player.id else "themselves"
            )

            if current_player_in_game.is_protected():
                logger_play_turn.warning(
                    "%s attacked %s but is occupied by %s and protected",
                    player.name,
                    tile,
                    current_player_name,
                )
                action.fail(reason=ActionFailureReason.ATTACK_PROTECTED)
                on_protected.add(player.id)
                continue

            old_level = occupied_tile.level
            distance = max(
                1,
                min(
                    tile.distance(Tile(col, row))
                    for col, row in player_in_game.occupiedtile_set.values_list("col", "row")
                ),
            )
            distance_efficiency = (
                (1 - game.config.attack_farthest_efficiency) * distance
                + game.config.attack_farthest_efficiency
                - grid.max_distance
            ) / (1 - grid.max_distance)
            occupied_tile.level -= (damage := game.config.attack_damage * action.efficiency * distance_efficiency)

            if occupied_tile.level <= 0:
                logger_play_turn.info(
                    "%s attacked and destroyed %s that was occupied by %s (damage: %s, from %s)",
                    player.name,
                    tile,
                    current_player_name,
                    f"{damage:.2f}",
                    f"{old_level:.2f}",
                )
                occupied_tile.delete()
                if not current_player_in_game.has_tiles():
                    logger_play_turn.warning("%s IS NOW DEAD", current_player_in_game.player.name)
                    current_player_in_game.die(turn=turn, killer=player_in_game)
                    dead_during_turn.add(current_player_in_game.id)
            else:
                occupied_tile.save()
                logger_play_turn.info(
                    "%s attacked %s that is occupied by %s (damage: %s, from %s to %s)",
                    player.name,
                    tile,
                    current_player_name,
                    f"{damage:.2f}",
                    f"{old_level:.2f}",
                    f"{occupied_tile.level:.2f}",
                )

            action.success()

        elif action.action_type == ActionType.DEFEND:
            if occupied_tile is None:
                logger_play_turn.warning("%s defended %s but it's not occupied", player.name, tile)
                action.fail(reason=ActionFailureReason.DEFEND_EMPTY)
                continue

            current_player_in_game = occupied_tile.player_in_game
            if current_player_in_game.player_id != player.id:
                logger_play_turn.warning(
                    "%s defended %s but it's occupied by %s", player.name, tile, current_player_in_game.player.name
                )
                action.fail(reason=ActionFailureReason.DEFEND_OTHER)
                continue

            old_level = occupied_tile.level
            occupied_tile.level += (improvement := game.config.defend_improvement * action.efficiency)
            occupied_tile.level = min(occupied_tile.level, 100.0)
            occupied_tile.save()
            logger_play_turn.info(
                "%s defended %s (improvement: %s, from %s to %s)",
                player.name,
                tile,
                f"{improvement:.2f}",
                f"{old_level:.2f}",
                f"{occupied_tile.level:.2f}",
            )

            action.success()

        elif action.action_type == ActionType.GROW:
            if occupied_tile is not None:
                current_player_in_game = occupied_tile.player_in_game

                if current_player_in_game.player_id == player.id:
                    logger_play_turn.warning("%s grew on %s but it's already his tile", player.name, tile)
                    action.fail(reason=ActionFailureReason.GROW_SELF)
                    continue

                if not game.config.can_grow_on_occupied:
                    logger_play_turn.warning(
                        "%s grew on %s but is occupied by %s",
                        player.name,
                        tile,
                        current_player_in_game.player.name,
                    )
                    action.fail(reason=ActionFailureReason.GROW_OCCUPIED)
                    continue

                if current_player_in_game.is_protected():
                    logger_play_turn.warning(
                        "%s grew on %s but is occupied by %s and protected",
                        player.name,
                        tile,
                        current_player_in_game.player.name,
                    )
                    action.fail(reason=ActionFailureReason.GROW_PROTECTED)
                    on_protected.add(player.id)
                    continue

            if (
                game.config.neighbors_only
                and player_in_game.has_tiles()
                and not OccupiedTile.has_occupied_neighbors(player_in_game.id, tile, grid)
            ):
                logger_play_turn.warning("%s grew on %s but has no neighbors", player.name, tile)
                action.fail(reason=ActionFailureReason.GROW_NO_NEIGHBOR)
                continue

            if occupied_tile is not None:
                current_player_in_game = occupied_tile.player_in_game
                logger_play_turn.info(
                    "%s grew on %s that was occupied by %s", player.name, tile, current_player_in_game.player.name
                )
                occupied_tile.player_in_game = player_in_game
                occupied_tile.save()

                if not current_player_in_game.has_tiles():
                    logger_play_turn.warning("%s IS NOW DEAD", current_player_in_game.player.name)
                    current_player_in_game.die(turn=turn, killer=player_in_game)
                    dead_during_turn.add(current_player_in_game.id)
            else:
                logger_play_turn.info("%s grew on %s that was not occupied", player.name, tile)
                OccupiedTile.objects.create(
                    game=game,
                    col=tile.col,
                    row=tile.row,
                    player_in_game=player_in_game,
                    level=game.config.tile_start_level * action.efficiency,
                )

            on_protected.discard(player.id)

            action.success()

    for player_id, (player, tile) in seen_in_turn.items():
        if player_id in seen_players_ids or player_id in dead_during_turn:
            continue
        if on_protected:
            messages.append(
                f"Bienvenue dans la partie @{player.name} ! "
                "Mais tu as cliqué sur une case protégée ! "
                "Essaye sur une case sans rond au milieu !"
            )
        else:
            messages.append(
                f"Bienvenue dans la partie @{player.name} ! "
                f"Tu vas apparaître en {human_coordinates(tile.col, tile.row)} dans quelques secondes ! "
                "Clique sur les cases autour pour t'agrandir (le délai est normal "
                "et tu n'es pas obligé·e d'attendre l'affichage d'une case cliquée pour continuer !)"
            )
            seen_players_ids.add(player.id)

    return messages


async def aplay_turn(game: Game, grid: Grid, seen_players_ids: set[int], turn: Optional[int] = None) -> list[str]:
    """Play a turn."""
    return cast(list[str], await sync_to_async(play_turn)(game, grid, seen_players_ids, turn))


def get_free_color(game: Game, default: Color) -> Color:
    """Get a color not already used in the game, using the default if not used, or no other available."""
    used_colors = {pig.color_object for pig in game.get_current_players_in_game()}
    if default not in used_colors:
        return default
    free_colors = set(PALETTE) - used_colors
    return free_colors.pop() if free_colors else default


def save_action(
    player: Player, game: Game, tile: Optional[Tile], action_type: ActionType = ActionType.GROW, efficiency: float = 1
) -> Optional[Action]:
    """Save the player action if they clicked one a tile."""
    if tile is None and action_type != ActionType.BANK:
        return None

    default_player_attrs = dict(  # noqa: C408
        started_turn=game.current_turn,
        start_tile_col=tile.col if tile else None,
        start_tile_row=tile.row if tile else None,
        level=game.config.player_start_level,
    )

    player_in_game = (
        game.playeringame_set.filter(
            player=player,
        )
        .order_by("-id")
        .first()
    )

    action_log_attrs: tuple[Any, ...]
    if action_type == ActionType.GROW:
        action_log = "grows in %s"
        action_log_attrs = (player.name, tile)
    elif action_type == ActionType.ATTACK:
        action_log = "attacks %s"
        action_log_attrs = (player.name, tile)
    elif action_type == ActionType.DEFEND:
        action_log = "defends %s"
        action_log_attrs = (player.name, tile)
    else:
        action_log = "bank"
        action_log_attrs = (player.name,)

    if player_in_game is None:
        player_in_game = PlayerInGame.objects.create(
            player=player,
            game=game,
            color=get_free_color(game, PALETTE[player.id % NB_COLORS]).as_hex,
            **default_player_attrs,
        )
        logger_save_action.warning(f"%s {action_log} AND IS A NEW PLAYER", *action_log_attrs)
    elif player_in_game.ended_turn is not None:
        if not player_in_game.can_respawn():
            logger_save_action.warning(f"%s {action_log} but IS STILL DEAD", *action_log_attrs)
            return None

        player_in_game = PlayerInGame.objects.create(
            player=player,
            game=game,
            color=get_free_color(game, player_in_game.color_object).as_hex,
            **default_player_attrs,
        )
        logger_save_action.warning(f"%s {action_log} AND IS ALIVE AGAIN", *action_log_attrs)
    elif player_in_game.get_available_actions() <= 0:
        logger_save_action.warning(f"%s {action_log} BUT HAS NOT ACTIONS LEFT", *action_log_attrs)
        return None
    else:
        logger_save_action.info(f"%s {action_log}", *action_log_attrs)

    return Action.objects.create(
        game=game,
        player_in_game=player_in_game,
        turn=game.current_turn,
        action_type=action_type,
        tile_col=tile.col if tile else None,
        tile_row=tile.row if tile else None,
        confirmed_at=timezone.now(),
        state=ActionState.CONFIRMED,
        efficiency=efficiency,
    )


async def asave_action(
    player: Player,
    game: Game,
    tile: Optional[Tile],
    action_type: ActionType = ActionType.GROW,
    efficiency: float = 1.0,
) -> Optional[Action]:
    """Save the player action if they clicked one a tile."""
    return cast(Optional[Action], await sync_to_async(save_action)(player, game, tile, action_type, efficiency))


async def on_click(  # pylint: disable=unused-argument
    player: Player, x_relative: float, y_relative: float, game: Game, grid: ConcreteGrid, clicks_queue: ClicksQueue
) -> None:
    """Display a message when a click is received."""
    target, point = get_click_target(x_relative, y_relative)
    if target == "grid-area":
        area = COORDINATES["grid-area"]
        tile = grid.get_tile_at_point(Point(x=point.x - area[0][0], y=point.y - area[0][1]))

        await clicks_queue.put((player, tile))
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
