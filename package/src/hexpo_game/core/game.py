"""Main game loop and functions."""

import asyncio
import logging
from asyncio import Queue
from datetime import timedelta
from string import ascii_letters
from typing import Any, NamedTuple, Optional, TypeAlias, cast

from asgiref.sync import sync_to_async
from django.db.models import Count
from django.utils import timezone

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .click_handler import COORDINATES, get_click_target
from .constants import (
    NB_COLORS,
    PALETTE,
    ActionFailureReason,
    ActionState,
    ActionType,
    ClickTarget,
    GameStep,
)
from .grid import ConcreteGrid, Grid
from .models import Action, Game, OccupiedTile, Player, PlayerInGame
from .twitch import ChatMessagesQueue
from .types import (
    Color,
    GameMessage,
    GameMessageKind,
    GameMessages,
    GameMessagesQueue,
    Point,
    Tile,
)

logger = logging.getLogger("hexpo_game.game")
logger_save_action = logging.getLogger("hexpo_game.game.save_action")
logger_play_turn = logging.getLogger("hexpo_game.game.play_turn")


class PlayerClick(NamedTuple):
    """A player click on a valid target."""

    player: Player
    target: ClickTarget
    tile: Optional[Tile]


ClicksQueue: TypeAlias = Queue[PlayerClick]


def human_coordinates(col: int, row: int) -> str:
    """Get the human coordinates."""
    return f"{ascii_letters[26:][row]}‑{col + 1}"


class GameLoop:  # pylint: disable=too-many-instance-attributes
    """Loop of the game, step by step, forever."""

    def __init__(
        self,
        clicks_queue: ClicksQueue,
        game: Game,
        grid: Grid,
        chat_messages_queue: ChatMessagesQueue,
        game_messages_queue: GameMessagesQueue,
        waiting_for_players_duration: Optional[timedelta] = None,
        collecting_actions_duration: Optional[timedelta] = None,
        go_next_turn_if_no_actions: bool = False,
    ):
        """Initialize the game loop."""
        self.clicks_queue: ClicksQueue = clicks_queue
        self.game: Game = game
        self.grid: Grid = grid
        self.chat_messages_queue: ChatMessagesQueue = chat_messages_queue
        self.game_messages_queue: GameMessagesQueue = game_messages_queue
        self.waiting_for_players_duration: timedelta = (
            game.config.step_waiting_for_players_duration
            if waiting_for_players_duration is None
            else waiting_for_players_duration
        )
        self.collecting_actions_duration: timedelta = (
            game.config.step_collecting_actions_duration
            if collecting_actions_duration is None
            else collecting_actions_duration
        )
        self.go_next_turn_if_no_actions: bool = go_next_turn_if_no_actions
        self.end_loop_event: asyncio.Event = asyncio.Event()
        self.end_step_event: asyncio.Event = asyncio.Event()

    async def step_waiting_for_players(self) -> None:
        """Wait for new players to join the game."""

    async def step_collecting_actions(self) -> None:
        """Collect actions from players."""
        next_turn_min_at = timezone.now() + self.collecting_actions_duration
        while True:
            if self.end_step_event.is_set() or self.end_loop_event.is_set():
                break
            if timezone.now() >= next_turn_min_at and (
                self.go_next_turn_if_no_actions or await self.game.confirmed_actions_for_turn().aexists()
            ):
                break
            try:
                player_click = await asyncio.wait_for(
                    self.clicks_queue.get(), timeout=min(1.0, self.collecting_actions_duration.total_seconds())
                )
            except asyncio.TimeoutError:
                continue
            else:
                try:
                    if (
                        player_click.target == ClickTarget.MAP
                    ):  # this is temporary as we do not handle clicks on buttons yet
                        await asave_action(player_click.player, self.game, player_click.tile)
                except Exception:  # pylint:disable=broad-except
                    logger.exception("Error while processing click for %s", player_click.player.name)
                self.clicks_queue.task_done()

    async def step_random_events_before(self) -> None:
        """Generate some random events after collecting the actions and before executing them."""

    async def step_executing_actions(self) -> None:
        """Execute the actions of the current turn."""
        messages = await aplay_turn(self.game, self.grid)
        await self.send_messages(messages)

    async def step_random_events_after(self) -> None:
        """Generate some random events after executing the actions."""

    async def send_messages(self, messages: GameMessages) -> None:
        """Send the messages to the game messages queue."""
        for message in messages:
            if message.chat_text is not None:
                await self.chat_messages_queue.put(message.chat_text)
            await self.game_messages_queue.put(message)

    async def run_current_step(self) -> None:
        """Run the current step."""
        self.end_step_event.clear()

        step = GameStep(self.game.current_turn_step)
        if self.game.config.multi_steps:
            await self.game_messages_queue.put(
                GameMessage(
                    text=f"Current step: {step.label}",
                    kind=GameMessageKind.GAME_STEP_CHANGED,
                    color=Color(255, 0, 0),
                )
            )
            logger.info("Current step: %s", step)

        if step == GameStep.WAITING_FOR_PLAYERS:
            await self.step_waiting_for_players()
        elif step == GameStep.COLLECTING_ACTIONS:
            await self.step_collecting_actions()
        elif step == GameStep.RANDOM_EVENTS_BEFORE:
            await self.step_random_events_before()
        elif step == GameStep.EXECUTING_ACTIONS:
            await self.step_executing_actions()
        elif step == GameStep.RANDOM_EVENTS_AFTER:
            await self.step_random_events_after()
        else:
            raise ValueError(f"Unknown step {step}")

    async def run(self) -> None:
        """Run the game loop."""
        while not self.end_loop_event.is_set() and not self.game.is_over():
            await self.run_current_step()
            await self.game.anext_step()  # will change the turn if needed

    async def end(self) -> None:
        """End the game loop."""
        self.end_loop_event.set()
        self.end_step_event.set()

        for _ in range(self.chat_messages_queue.qsize()):
            self.chat_messages_queue.get_nowait()
            self.chat_messages_queue.task_done()

        for _ in range(self.game_messages_queue.qsize()):
            self.game_messages_queue.get_nowait()
            self.game_messages_queue.task_done()


class PlayerInGameExtra(NamedTuple):
    """A type to help mypy understand data retrieved with annotated values from the database."""

    nb_tiles: int


def play_turn(  # pylint:disable=too-many-locals,too-many-branches,too-many-statements
    game: Game, grid: Grid, turn: Optional[int] = None
) -> GameMessages:
    """Play a turn."""
    turn = game.current_turn if turn is None else turn
    queryset = game.confirmed_actions_for_turn(turn)
    logger_play_turn.info("Playing turn %s: %s actions", turn, len(queryset))

    dead_during_turn: set[int] = set()

    messages: GameMessages = []

    def new_death(player_in_game: PlayerInGame, killer: PlayerInGame) -> None:
        logger_play_turn.warning("%s IS NOW DEAD", player_in_game.player.name)
        player_in_game.die(turn=turn, killer=killer)
        dead_during_turn.add(player_in_game.id)
        messages.append(
            GameMessage(
                f"{player_in_game.player.name} a péri sous l'assaut de {killer.player.name}",
                kind=GameMessageKind.DEATH,
                color=player_in_game.color_object,
            )
        )

    for action in queryset.order_by("confirmed_at"):

        if (action.tile_col is None or action.tile_row is None) and action.action_type != ActionType.BANK:
            continue

        # as the player can be changed by previous actions, we need to load it from db for each action
        player_in_game = (
            PlayerInGame.objects.filter(id=action.player_in_game_id)
            .select_related("player")
            .annotate(nb_tiles=Count("occupiedtile"))
            .get()
        )
        player = player_in_game.player

        if player_in_game.id in dead_during_turn:
            action.fail(reason=ActionFailureReason.DEAD)
            logger_play_turn.warning("%s IS DEAD (killed in this turn)", player.name)
            continue

        if not player_in_game.nb_tiles and action.action_type != ActionType.GROW:
            action.fail(reason=ActionFailureReason.BAD_FIRST)
            logger_play_turn.warning(
                "%s had no tiles but did a wrong first action: %s", player.name, action.action_type
            )
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
        occupied_tile = (
            OccupiedTile.objects.filter(game=game, col=tile.col, row=tile.row)
            .select_related("player_in_game__player")
            .annotate(occupier_nb_tiles=Count("player_in_game__occupiedtile"))
            .first()
        )

        if action.action_type == ActionType.ATTACK:
            if occupied_tile is None:
                logger_play_turn.warning("%s attacked %s but it's not occupied", player.name, tile)
                action.fail(reason=ActionFailureReason.ATTACK_EMPTY)
                continue

            if occupied_tile.player_in_game_id == player_in_game.id:
                logger_play_turn.warning("%s attacked %s but it's their own", player.name, tile)
                action.fail(reason=ActionFailureReason.ATTACK_SELF)
                continue

            if occupied_tile.player_in_game.is_protected(occupied_tile.occupier_nb_tiles):
                logger_play_turn.warning(
                    "%s attacked %s but it's occupied by %s and protected",
                    player.name,
                    tile,
                    occupied_tile.player_in_game.player.name,
                )
                action.fail(reason=ActionFailureReason.ATTACK_PROTECTED)
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
                    occupied_tile.player_in_game.player.name,
                    f"{damage:.2f}",
                    f"{old_level:.2f}",
                )
                if occupied_tile.occupier_nb_tiles <= 1:
                    new_death(occupied_tile.player_in_game, player_in_game)
                occupied_tile.delete()
            else:
                occupied_tile.save()
                logger_play_turn.info(
                    "%s attacked %s that is occupied by %s (damage: %s, from %s to %s)",
                    player.name,
                    tile,
                    occupied_tile.player_in_game.player.name,
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

            if occupied_tile.player_in_game_id != player_in_game.id:
                logger_play_turn.warning(
                    "%s defended %s but it's occupied by %s",
                    player.name,
                    tile,
                    occupied_tile.player_in_game.player.name,
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
            if occupied_tile is not None and occupied_tile.player_in_game_id == player_in_game.id:
                logger_play_turn.warning("%s grew on %s but it's already their tile", player.name, tile)
                action.fail(reason=ActionFailureReason.GROW_SELF)
                continue

            if (
                game.config.neighbors_only
                and player_in_game.nb_tiles
                and not OccupiedTile.has_occupied_neighbors(player_in_game.id, tile, grid)
            ):
                logger_play_turn.warning("%s grew on %s but has no neighbors", player.name, tile)
                action.fail(reason=ActionFailureReason.GROW_NO_NEIGHBOR)
                continue

            if occupied_tile is not None:
                if not game.config.can_grow_on_occupied:
                    logger_play_turn.warning(
                        "%s %s on %s but it's occupied by %s",
                        player.name,
                        "grew" if player_in_game.nb_tiles else "started",
                        tile,
                        occupied_tile.player_in_game.player.name,
                    )
                    action.fail(reason=ActionFailureReason.GROW_OCCUPIED)
                    if not player_in_game.nb_tiles:
                        messages.append(
                            GameMessage(
                                text=f"{player_in_game.player.name} n'a pu "
                                f"{'commencer' if player_in_game.first_in_game_for_player else 'revenir'} "
                                f"en {human_coordinates(tile.col, tile.row)} (case occupée)",
                                kind=GameMessageKind.SPAWN_FAILED,
                                color=player_in_game.color_object,
                                player_id=player.id,
                                chat_text=None
                                if player.welcome_chat_message_sent_at
                                else (
                                    f"Bienvenue dans la partie @{player_in_game.player.name} ! "
                                    "Mais tu as cliqué sur une case occupée ! "
                                    "Essaye sur une case libre !"
                                ),
                            )
                        )
                    continue

                if occupied_tile.player_in_game.is_protected():
                    logger_play_turn.warning(
                        "%s %s on %s but it's occupied by %s and protected",
                        player.name,
                        "grew" if player_in_game.nb_tiles else "started",
                        tile,
                        occupied_tile.player_in_game.player.name,
                    )
                    action.fail(reason=ActionFailureReason.GROW_PROTECTED)
                    if not player_in_game.nb_tiles:
                        messages.append(
                            GameMessage(
                                text=f"{player_in_game.player.name} n'a pu "
                                f"{'commencer' if player_in_game.first_in_game_for_player else 'revenir'} "
                                f"en {human_coordinates(tile.col, tile.row)} (case protégée)",
                                kind=GameMessageKind.SPAWN_FAILED,
                                color=player_in_game.color_object,
                                player_id=player.id,
                                chat_text=None
                                if player.welcome_chat_message_sent_at
                                else (
                                    f"Bienvenue dans la partie @{player_in_game.player.name} ! "
                                    "Mais tu as cliqué sur une case protégée ! "
                                    "Essaye sur une case sans rond au milieu !"
                                ),
                            )
                        )

                    continue

                logger_play_turn.info(
                    "%s grew on %s that was occupied by %s",
                    player.name,
                    tile,
                    occupied_tile.player_in_game.player.name,
                )
                if occupied_tile.occupier_nb_tiles <= 1:
                    new_death(occupied_tile.player_in_game, player_in_game)
                occupied_tile.player_in_game = player_in_game
                occupied_tile.save()
            else:
                logger_play_turn.info("%s grew on %s that was not occupied", player.name, tile)
                OccupiedTile.objects.create(
                    game=game,
                    col=tile.col,
                    row=tile.row,
                    player_in_game=player_in_game,
                    level=game.config.tile_start_level * action.efficiency,
                )

            if not player_in_game.nb_tiles:
                messages = [
                    message
                    for message in messages
                    if message.player_id != player.id or message.kind != GameMessageKind.SPAWN_FAILED
                ]
                messages.append(
                    GameMessage(
                        text=f"{player_in_game.player.name} "
                        f"{'arrive' if player_in_game.first_in_game_for_player else 'est de retour'} "
                        f"en {human_coordinates(tile.col, tile.row)}",
                        kind=GameMessageKind.SPAWN,
                        color=player_in_game.color_object,
                        player_id=player.id,
                        chat_text=None
                        if player.welcome_chat_message_sent_at
                        else (
                            f"Bienvenue dans la partie @{player_in_game.player.name} ! "
                            f"Tu commences en {human_coordinates(tile.col, tile.row)} ! "
                            "Au prochain tour tu pourras t'aggrandir, te défendre ou attaquer !"
                        )
                        if game.config.multi_steps
                        else (
                            f"Bienvenue dans la partie @{player_in_game.player.name} ! "
                            f"Tu vas apparaître en {human_coordinates(tile.col, tile.row)} dans quelques secondes ! "
                            "Clique sur les cases autour pour t'agrandir (le délai est normal "
                            "et tu n'es pas obligé·e d'attendre l'affichage d'une case cliquée pour continuer !)"
                        ),
                    )
                )
                if not player.welcome_chat_message_sent_at:
                    player.welcome_chat_message_sent_at = timezone.now()
                    player.save()

            player_in_game.reset_start_tile(tile.col, tile.row)

            action.success()

    return messages


async def aplay_turn(game: Game, grid: Grid, turn: Optional[int] = None) -> GameMessages:
    """Play a turn."""
    return cast(GameMessages, await sync_to_async(play_turn)(game, grid, turn))


def get_free_color(game: Game, default: Color) -> Color:
    """Get a color not already used in the game, using the default if not used, or no other available."""
    used_colors = {pig.color_object for pig in game.get_current_players_in_game()}
    if default not in used_colors:
        return default
    free_colors = set(PALETTE) - used_colors
    return free_colors.pop() if free_colors else default


def save_action(  # pylint: disable=too-many-return-statements,too-many-branches
    player: Player, game: Game, tile: Optional[Tile], action_type: ActionType = ActionType.GROW, efficiency: float = 1
) -> Optional[Action]:
    """Save the player action if they clicked one a tile."""
    if tile is None and action_type != ActionType.BANK:
        return None

    default_player_attrs = dict(  # noqa: C408
        started_turn=game.current_turn,
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
        if action_type != ActionType.GROW:
            logger_save_action.warning(f"%s cannot {action_log} AS A NEW PLAYER", *action_log_attrs)
            return None
        player_in_game = PlayerInGame.objects.create(
            player=player,
            game=game,
            color=get_free_color(game, PALETTE[player.id % NB_COLORS]).as_hex,
            first_in_game_for_player=True,
            **default_player_attrs,
        )
        logger_save_action.warning(f"%s {action_log} AND IS A NEW PLAYER", *action_log_attrs)
    elif player_in_game.ended_turn is not None:
        if not player_in_game.can_respawn():
            logger_save_action.warning(f"%s {action_log} but IS STILL DEAD", *action_log_attrs)
            return None
        if action_type != ActionType.GROW:
            logger_save_action.warning(f"%s cannot {action_log} AS A RETURNING PLAYER", *action_log_attrs)
            return None

        player_in_game = PlayerInGame.objects.create(
            player=player,
            game=game,
            color=get_free_color(game, player_in_game.color_object).as_hex,
            first_in_game_for_player=False,
            **default_player_attrs,
        )
        logger_save_action.warning(f"%s {action_log} AND IS ALIVE AGAIN", *action_log_attrs)
    elif player_in_game.get_available_actions() <= 0:
        logger_save_action.warning(f"%s {action_log} BUT HAS NOT ACTIONS LEFT", *action_log_attrs)
        return None
    else:
        if player_in_game.start_tile_col is None and action_type != ActionType.GROW:
            logger_save_action.warning(
                f"%s cannot {action_log} AS A %s PLAYER",
                *action_log_attrs,
                "NEW" if player_in_game.first_in_game_for_player else "RETURNING",
            )
            return None

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
    if target == ClickTarget.MAP:
        area = COORDINATES[target]
        tile = grid.get_tile_at_point(Point(x=point.x - area[0][0], y=point.y - area[0][1]))
        await clicks_queue.put(PlayerClick(player, target, tile))
    elif target is not None:
        await clicks_queue.put(PlayerClick(player, target, None))


def get_game_and_grid() -> tuple[Game, ConcreteGrid]:
    """Get the current game."""
    area = COORDINATES[ClickTarget.MAP]
    width = area[1][0] - area[0][0]
    height = area[1][1] - area[0][1]
    nb_cols, nb_rows, tile_size = ConcreteGrid.compute_grid_size(500, width, height)
    game = Game.get_current(nb_cols=nb_cols, nb_rows=nb_rows)
    grid = ConcreteGrid(Grid(nb_cols, nb_rows), tile_size)
    return game, grid
