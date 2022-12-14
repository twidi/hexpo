"""Main game loop and functions."""
# pylint: disable=too-many-lines

import asyncio
import logging
from asyncio import Queue
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timedelta
from queue import Empty
from random import choice
from typing import Any, Callable, Coroutine, NamedTuple, Optional, TypeAlias, cast

from asgiref.sync import sync_to_async
from django.db.models import Avg, Count
from django.utils import timezone

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .click_handler import COORDINATES, get_click_target
from .constants import (
    EROSION_DAMAGES_ACTIVE_PLAYER,
    EROSION_DAMAGES_INACTIVE_PLAYER,
    LATENCY_DELAY,
    NB_COLORS,
    NO_EVENT_MESSAGES,
    PALETTE,
    ActionFailureReason,
    ActionState,
    ActionType,
    ButtonToAction,
    ClickTarget,
    GameEndMode,
    GameMode,
    GameStep,
    RandomEventType,
)
from .grid import ConcreteGrid, Grid
from .models import Action, Game, OccupiedTile, Player, PlayerInGame, RandomEvent
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
logger_new_players = logging.getLogger("hexpo_game.game.players")
logger_collect = logging.getLogger("hexpo_game.game.collect")
logger_events = logging.getLogger("hexpo_game.game.events")
logger_execute = logging.getLogger("hexpo_game.game.execute")
logger_erosion = logging.getLogger("hexpo_game.game.erosion")


class PlayerClick(NamedTuple):
    """A player click on a valid target."""

    player: Player
    target: ClickTarget
    tile: Optional[Tile]


ClicksQueue: TypeAlias = Queue[PlayerClick]


class GameLoop:  # pylint: disable=too-many-instance-attributes, too-many-arguments
    """Loop of the game, step by step, forever."""

    def __init__(
        self,
        clicks_queue: ClicksQueue,
        clicks_allowed_event: asyncio.Event,
        game: Game,
        grid: Grid,
        chat_messages_queue: ChatMessagesQueue,
        game_messages_queue: GameMessagesQueue,
        waiting_for_players_duration: Optional[timedelta] = None,
        collecting_actions_duration: Optional[timedelta] = None,
        latency_delay: timedelta = LATENCY_DELAY,
        go_next_turn_if_no_actions: bool = False,
    ):
        """Initialize the game loop."""
        self.clicks_queue: ClicksQueue = clicks_queue
        self.clicks_allowed_event: asyncio.Event = clicks_allowed_event
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
        self.latency_delay: timedelta = latency_delay
        self.go_next_turn_if_no_actions: bool = go_next_turn_if_no_actions
        self.end_loop_event: asyncio.Event = asyncio.Event()
        self.end_step_event: asyncio.Event = asyncio.Event()

    async def step_waiting_for_players(self) -> None:
        """Wait for new players to join the game."""
        if not self.game.config.multi_steps or await self.game.occupiedtile_set.acount() == self.grid.nb_tiles:
            return
        end_step_at = await self.game.areset_step_times(update_start=True, duration=self.waiting_for_players_duration)
        if self.game.config.multi_steps:
            end_step_at += self.latency_delay
        self.clicks_allowed_event.set()
        while True:
            if self.end_step_event.is_set() or self.end_loop_event.is_set():
                break
            if timezone.now() >= end_step_at:
                # we need at least two players to continue the game
                if await self.game.get_current_players_in_game().acount() >= 2:
                    break
                end_step_at = await self.game.areset_step_times(
                    update_start=False, duration=self.waiting_for_players_duration
                )
                if self.game.config.multi_steps:
                    end_step_at += self.latency_delay
            try:
                player_click = await asyncio.wait_for(
                    self.clicks_queue.get(), timeout=min(1.0, self.waiting_for_players_duration.total_seconds())
                )
            except asyncio.TimeoutError:
                continue
            else:
                try:
                    messages = await sync_to_async(self.step_waiting_for_players_handle_click)(
                        player_click, self.game, self.grid
                    )
                    if messages:
                        await self.send_messages(messages)
                except Exception:  # pylint:disable=broad-except
                    logger.exception("Error while processing click for %s", player_click.player.name)
                self.clicks_queue.task_done()

    @classmethod
    def step_waiting_for_players_handle_click(cls, player_click: PlayerClick, game: Game, grid: Grid) -> GameMessages:
        """Handle a click during the waiting for players step."""
        player, target, tile = player_click.player, player_click.target, player_click.tile
        if target != ClickTarget.MAP or tile is None:
            return []
        player_in_game = get_or_create_player_in_game(player, game, allow_new=True, allow_existing=False)
        if player_in_game is None:
            return []
        # a user entering the game is like in the single step mode where the user clicks a tile
        action = cls.step_collecting_actions_handle_click_single_step(player_click, game)
        if action is None:
            return []
        messages = execute_action(action, game, grid, game.current_turn, defaultdict(int), set())
        action.refresh_from_db()
        if action.state == ActionState.FAILURE:
            player_in_game.die()
        return messages

    async def step_collecting_actions(self) -> None:  # pylint: disable=too-many-branches
        """Collect actions from players."""
        self.clicks_allowed_event.set()
        end_step_at = await self.game.areset_step_times(update_start=True, duration=self.collecting_actions_duration)
        if self.game.config.multi_steps:
            end_step_at += self.latency_delay
        while True:
            if self.end_step_event.is_set() or self.end_loop_event.is_set():
                break
            if timezone.now() >= end_step_at:
                break
            try:
                player_click = await asyncio.wait_for(
                    self.clicks_queue.get(), timeout=min(1.0, self.collecting_actions_duration.total_seconds())
                )
            except asyncio.TimeoutError:
                continue
            else:
                try:
                    if self.game.config.multi_steps:
                        action = await sync_to_async(self.step_collecting_actions_handle_click_multi_steps)(
                            player_click, self.game
                        )
                        if action is not None and action.confirmed_at is not None:
                            await sync_to_async(self.step_collecting_actions_compute_efficiency)(self.game)
                    else:
                        await sync_to_async(self.step_collecting_actions_handle_click_single_step)(
                            player_click, self.game
                        )
                except Exception:  # pylint:disable=broad-except
                    logger.exception("Error while processing click for %s", player_click.player.name)
                self.clicks_queue.task_done()

        if self.game.config.multi_steps:
            await sync_to_async(self.step_collecting_actions_compute_efficiency)(self.game)

    @classmethod
    def step_collecting_actions_handle_click_single_step(
        cls, player_click: PlayerClick, game: Game
    ) -> Optional[Action]:
        """Handle a click for a single step game."""
        player, target, tile = player_click.player, player_click.target, player_click.tile
        if target != ClickTarget.MAP or tile is None:
            return None
        player_in_game = get_or_create_player_in_game(player, game, allow_new=True, allow_existing=True)
        if player_in_game is None:
            return None
        if not can_create_action(player_in_game):
            return None
        if (action := create_or_update_action(player_in_game, game, ActionType.GROW)) is None:
            return None
        set_action_tile(player_in_game, game, tile, action=action)
        confirm_action(player_in_game, game, action=action)
        return action

    @classmethod
    def step_collecting_actions_handle_click_multi_steps(
        cls, player_click: PlayerClick, game: Game
    ) -> Optional[Action]:
        """Handle a click for a multi steps game."""
        player, target, tile = player_click.player, player_click.target, player_click.tile
        player_in_game = get_or_create_player_in_game(player, game, allow_new=False, allow_existing=True)
        if player_in_game is None:
            return None
        if not can_create_action(player_in_game):
            return None
        if (action_type := ButtonToAction.get(target)) is not None:
            return create_or_update_action(player_in_game, game, action_type)
        if target == ClickTarget.MAP and tile is not None:
            return set_action_tile(player_in_game, game, tile)
        if target == ClickTarget.BTN_CONFIRM:
            return confirm_action(player_in_game, game)
        return None

    @classmethod
    def step_collecting_actions_compute_efficiency(cls, game: Game) -> None:
        """Compute the efficiency of the actions.

        We assign an efficiency for each action, the oldest action has the max efficiency and the newest the min,
        the efficiency is decreasing using the difference in time between two actions.
        """
        actions = list(game.confirmed_actions_for_turn(game.current_turn).order_by("confirmed_at"))
        if len(actions) <= 1:
            return
        # we can cast to datetime because we have a constraint on the database to ensure that confirmed_at is not null
        # when the state is ActionState.CONFIRMED
        first_date = cast(datetime, actions[0].confirmed_at)
        last_date = cast(datetime, actions[-1].confirmed_at)
        if first_date == last_date:
            return
        max_efficiency = 1
        min_efficiency = 0.5
        if len(actions) == 2:
            actions[0].efficiency = max_efficiency
            actions[0].save()
            actions[1].efficiency = min_efficiency
            actions[1].save()
            return
        total_duration = (last_date - first_date).total_seconds()
        for i, action in enumerate(actions):
            if i == 0:
                action.efficiency = max_efficiency
            else:
                action.efficiency = (
                    max_efficiency
                    - (max_efficiency - min_efficiency)
                    * (cast(datetime, action.confirmed_at) - first_date).total_seconds()
                    / total_duration
                )
            action.save()

    async def step_random_events(self) -> None:
        """Generate some random events after collecting the actions and before executing them."""
        if not self.game.config.multi_steps:
            return
        _, messages = await sync_to_async(run_random_events)(self.game, self.grid)
        if messages:
            await self.send_messages(messages)
        if self.game.config.multi_steps:
            await asyncio.sleep(self.game.config.message_delay.total_seconds() * (len(messages) + 3))

    async def step_erosion(self) -> None:
        """Erode borders of players maps."""
        if not self.game.config.multi_steps:
            return
        _, messages = await sync_to_async(erode_map)(self.game, self.grid)
        messages.extend(await update_levels(self.game))
        if messages:
            await self.send_messages(messages)
        if self.game.config.multi_steps:
            await asyncio.sleep(self.game.config.message_delay.total_seconds() * (len(messages) + 3))

    async def step_executing_actions(self) -> None:
        """Execute the actions of the current turn."""
        if self.game.config.multi_steps:
            await asyncio.sleep(self.game.config.message_delay.total_seconds())
        messages = await aplay_turn(self.game, self.grid, send_messages=self.send_messages)
        if messages:
            await self.send_messages(messages)

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
                    text=step.label,
                    kind=GameMessageKind.GAME_STEP_CHANGED,
                )
            )
            logger.info("Current step: %s", step)

        if step == GameStep.WAITING_FOR_PLAYERS:
            await self.step_waiting_for_players()
        elif step == GameStep.COLLECTING_ACTIONS:
            await self.step_collecting_actions()
        elif step == GameStep.RANDOM_EVENTS:
            await self.step_random_events()
        elif step == GameStep.EXECUTING_ACTIONS:
            await self.step_executing_actions()
        elif step == GameStep.EROSION:
            await self.step_erosion()
        else:
            raise ValueError(f"Unknown step {step}")

        self.clicks_allowed_event.clear()
        with suppress(Empty):
            for _ in range(self.clicks_queue.qsize()):
                self.clicks_queue.get_nowait()
                self.clicks_queue.task_done()

    async def run(self) -> None:
        """Run the game loop."""
        current_turn = self.game.current_turn
        game_is_over = False
        while not self.end_loop_event.is_set() and not (game_is_over := await self.game.ais_over()):
            await self.run_current_step()
            force_step = None
            if (
                self.game.config.multi_steps
                and self.game.current_turn_step == GameStep.COLLECTING_ACTIONS
                and not self.go_next_turn_if_no_actions
                and not await self.game.confirmed_actions_for_turn().aexists()
            ):
                force_step = GameStep.WAITING_FOR_PLAYERS
            await self.game.anext_step(force_step)  # will change the turn if needed
            if self.game.current_turn != current_turn:
                current_turn = self.game.current_turn
                if self.game.config.multi_steps:
                    await self.game_messages_queue.put(
                        GameMessage(
                            text=f"Tour {current_turn}",
                            kind=GameMessageKind.GAME_TURN_CHANGED,
                        )
                    )
                    logger.info("New turn: %s", current_turn)

        if game_is_over:
            logger.info("Game is over")
            await self.game_messages_queue.put(
                GameMessage(
                    text="Partie terminée",
                    kind=GameMessageKind.GAME_OVER,
                )
            )
            winner = cast(PlayerInGame, await sync_to_async(lambda: self.game.winner)())
            if self.game.end_mode == GameEndMode.FULL_MAP:
                winner_nb_tiles = self.grid.nb_tiles
            else:
                winner_nb_tiles = sync_to_async(winner.count_tiles)()
            await self.game_messages_queue.put(
                GameMessage(
                    text=f"Le gagnant est {winner.player.name}",
                    kind=GameMessageKind.GAME_OVER,
                    color=winner.color_object,
                    player_id=winner.player_id,
                    chat_text=f"Le gagnant de la partie est @{winner.player.name} "
                    f"avec {winner_nb_tiles} cases conquises en {self.game.current_turn} tours !",
                )
            )

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


def execute_action(  # pylint:disable=too-many-locals,too-many-branches,too-many-statements,too-many-return-statements
    action: Action, game: Game, grid: Grid, turn: int, nb_actions: dict[int, int], dead_during_turn: set[int]
) -> GameMessages:
    """Execute the action."""
    # pycharm: disable = redefine-outer-name
    logger = (  # pylint:disable=redefined-outer-name
        logger_new_players if game.current_turn_step == GameStep.WAITING_FOR_PLAYERS else logger_execute
    )
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
        logger.warning("%s IS DEAD (killed in this turn)", player.name)
        return []

    nb_actions[player_in_game.id] += 1
    if nb_actions[player_in_game.id] > player_in_game.level + player_in_game.banked_actions:
        logger.warning(
            "%s USED TOO MANY ACTIONS (%s used, level %s, banked %s)",
            player.name,
            nb_actions[player_in_game.id],
            player_in_game.level,
            player_in_game.banked_actions,
        )
        return []

    if (action.tile_col is None or action.tile_row is None) and action.action_type != ActionType.BANK:
        return []

    if not player_in_game.nb_tiles and action.action_type != ActionType.GROW:
        action.fail(reason=ActionFailureReason.BAD_FIRST)
        logger.warning("%s had no tiles but did a wrong first action: %s", player.name, action.action_type)
        return []

    messages: GameMessages = []

    def add_message(
        player_in_game: PlayerInGame, text: str, kind: GameMessageKind = GameMessageKind.ACTION, always: bool = False
    ) -> None:
        if always or (game.config.multi_steps and game.current_turn_step != GameStep.WAITING_FOR_PLAYERS):
            messages.append(
                GameMessage(text, kind=kind, color=player_in_game.color_object, player_id=player_in_game.player_id)
            )

    def new_death(player_in_game: PlayerInGame, killer: PlayerInGame) -> None:
        logger.warning("%s IS NOW DEAD", player_in_game.player.name)
        player_in_game.die(turn=turn, killer=killer)
        dead_during_turn.add(player_in_game.id)
        add_message(
            player_in_game,
            f"{player_in_game.player.name} a disparu de la carte, bravo {killer.player.name}",
            GameMessageKind.DEATH,
            always=True,
        )

    if action.action_type == ActionType.BANK:
        old_banked = player_in_game.banked_actions
        player_in_game.banked_actions += (banked := game.config.bank_value * action.efficiency)
        player_in_game.save()
        action.success()
        logger.info(
            "%s banked %s (from %s to %s)",
            player.name,
            f"{banked:.2f}",
            f"{old_banked:.2f}",
            f"{player_in_game.banked_actions:.2f}",
        )
        add_message(player_in_game, f"{player_in_game.player.name} a mis de côté {banked:.2f} points d'actions")
        return messages

    tile = Tile(action.tile_col, action.tile_row)  # type: ignore[arg-type]  # we know we have a tile
    occupied_tile = (
        OccupiedTile.objects.filter(game=game, col=tile.col, row=tile.row)
        .select_related("player_in_game__player")
        .annotate(occupier_nb_tiles=Count("player_in_game__occupiedtile"))
        .first()
    )
    tile_dist_compensation = grid.tile_distance_from_origin_compensation(tile) if game.config.multi_steps else 0.0

    if action.action_type == ActionType.ATTACK:
        if occupied_tile is None:
            logger.warning("%s attacked %s but it's not occupied", player.name, tile.for_human())
            action.fail(reason=ActionFailureReason.ATTACK_EMPTY)
            add_message(
                player_in_game,
                f"{player_in_game.player.name} a attaqué en vain en {tile.for_human()} non occupée",
            )
            return messages

        if occupied_tile.player_in_game_id == player_in_game.id:
            logger.warning("%s attacked %s but it's their own", player.name, tile.for_human())
            add_message(
                player_in_game, f"{player_in_game.player.name} a attaqué en vain chez lui en {tile.for_human()}"
            )
            action.fail(reason=ActionFailureReason.ATTACK_SELF)
            return messages

        if occupied_tile.player_in_game.is_protected(occupied_tile.occupier_nb_tiles):
            logger.warning(
                "%s attacked %s but it's occupied by %s and protected",
                player.name,
                tile.for_human(),
                occupied_tile.player_in_game.player.name,
            )
            action.fail(reason=ActionFailureReason.ATTACK_PROTECTED)
            add_message(
                player_in_game, f"{player_in_game.player.name} a attaqué en vain en {tile.for_human()} protégée"
            )
            return messages

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
        occupied_tile.level -= (
            damage := game.config.attack_damage * action.efficiency * distance_efficiency + tile_dist_compensation
        )

        if occupied_tile.level <= 0:
            logger.info(
                "%s attacked and destroyed %s that was occupied by %s (damage: %s, from %s)",
                player.name,
                tile.for_human(),
                occupied_tile.player_in_game.player.name,
                f"{damage:.2f}",
                f"{old_level:.2f}",
            )
            add_message(
                player_in_game,
                f"{player_in_game.player.name} a libéré {tile.for_human()} "
                f"des mains de {occupied_tile.player_in_game.player.name}",
            )
            if occupied_tile.occupier_nb_tiles <= 1:
                new_death(occupied_tile.player_in_game, player_in_game)
            occupied_tile.delete()
        else:
            occupied_tile.save()
            logger.info(
                "%s attacked %s that is occupied by %s (damage: %s, from %s to %s)",
                player.name,
                tile.for_human(),
                occupied_tile.player_in_game.player.name,
                f"{damage:.2f}",
                f"{old_level:.2f}",
                f"{occupied_tile.level:.2f}",
            )
            # noinspection InvisibleCharacter
            add_message(
                player_in_game,
                f"{player_in_game.player.name} a attaqué {occupied_tile.player_in_game.player.name} "
                f"en {tile.for_human()} (-{damage:.2f} PV ➔ {occupied_tile.level:.2f})",
            )

        action.success()

    elif action.action_type == ActionType.DEFEND:
        if occupied_tile is None:
            logger.warning("%s defended %s but it's not occupied", player.name, tile.for_human())
            action.fail(reason=ActionFailureReason.DEFEND_EMPTY)
            add_message(
                player_in_game,
                f"{player_in_game.player.name} a défendu en vain en {tile.for_human()} non occupée",
            )
            return messages

        if occupied_tile.player_in_game_id != player_in_game.id:
            logger.warning(
                "%s defended %s but it's occupied by %s",
                player.name,
                tile.for_human(),
                occupied_tile.player_in_game.player.name,
            )
            add_message(
                player_in_game,
                f"{player_in_game.player.name} a défendu en vain en {tile.for_human()} "
                f"chez {occupied_tile.player_in_game.player.name}",
            )
            action.fail(reason=ActionFailureReason.DEFEND_OTHER)
            return messages

        old_level = occupied_tile.level
        occupied_tile.level += (
            improvement := game.config.defend_improvement * action.efficiency + tile_dist_compensation
        )
        occupied_tile.level = min(occupied_tile.level, 100.0)
        occupied_tile.save()
        logger.info(
            "%s defended %s (improvement: %s, from %s to %s)",
            player.name,
            tile.for_human(),
            f"{improvement:.2f}",
            f"{old_level:.2f}",
            f"{occupied_tile.level:.2f}",
        )
        # noinspection InvisibleCharacter
        add_message(
            player_in_game,
            f"{player_in_game.player.name} a défendu en {tile.for_human()} "
            f"(+{improvement:.2f} PV ➔ {occupied_tile.level:.2f})",
        )

        action.success()

    elif action.action_type == ActionType.GROW:
        if occupied_tile is not None and occupied_tile.player_in_game_id == player_in_game.id:
            logger.warning("%s grew on %s but it's already their tile", player.name, tile.for_human())
            action.fail(reason=ActionFailureReason.GROW_SELF)
            add_message(
                player_in_game, f"{player_in_game.player.name} n'a pu s'agrandir chez lui en {tile.for_human()}"
            )
            return messages

        if (
            game.config.neighbors_only
            and player_in_game.nb_tiles
            and not OccupiedTile.has_occupied_neighbors(player_in_game.id, tile, grid)
        ):
            logger.warning("%s grew on %s but has no neighbors", player.name, tile.for_human())
            add_message(
                player_in_game, f"{player_in_game.player.name} n'a pu s'agrandir en {tile.for_human()}, trop loin"
            )
            action.fail(reason=ActionFailureReason.GROW_NO_NEIGHBOR)
            return messages

        if occupied_tile is not None:
            if not game.config.can_grow_on_occupied:
                logger.warning(
                    "%s %s on %s but it's occupied by %s",
                    player.name,
                    "grew" if player_in_game.nb_tiles else "started",
                    tile.for_human(),
                    occupied_tile.player_in_game.player.name,
                )
                action.fail(reason=ActionFailureReason.GROW_OCCUPIED)
                if not player_in_game.nb_tiles:
                    messages.append(
                        GameMessage(
                            text=f"{player_in_game.player.name} n'a pu "
                            f"{'commencer' if player_in_game.first_in_game_for_player else 'revenir'} "
                            f"en {tile.for_human()} occupée",
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
                else:
                    add_message(
                        player_in_game,
                        f"{player_in_game.player.name} n'a pu s'agrandir en {tile.for_human()} "
                        f"chez {occupied_tile.player_in_game.player.name}",
                    )
                return messages

            if occupied_tile.player_in_game.is_protected():
                logger.warning(
                    "%s %s on %s but it's occupied by %s and protected",
                    player.name,
                    "grew" if player_in_game.nb_tiles else "started",
                    tile.for_human(),
                    occupied_tile.player_in_game.player.name,
                )
                action.fail(reason=ActionFailureReason.GROW_PROTECTED)
                if not player_in_game.nb_tiles:
                    messages.append(
                        GameMessage(
                            text=f"{player_in_game.player.name} n'a pu "
                            f"{'commencer' if player_in_game.first_in_game_for_player else 'revenir'} "
                            f"en {tile.for_human()} protégee",
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
                else:
                    add_message(
                        player_in_game,
                        f"{player_in_game.player.name} n'a pu s'agrandir en {tile.for_human()} "
                        f"chez {occupied_tile.player_in_game.player.name}, protégée",
                    )

                return messages

            logger.info(
                "%s grew on %s that was occupied by %s",
                player.name,
                tile.for_human(),
                occupied_tile.player_in_game.player.name,
            )
            if occupied_tile.occupier_nb_tiles <= 1:
                new_death(occupied_tile.player_in_game, player_in_game)
            occupied_tile.player_in_game = player_in_game
            occupied_tile.save()
            add_message(
                player_in_game,
                f"{player_in_game.player.name} s'est agrandi en {tile.for_human()} "
                f"chez {occupied_tile.player_in_game.player.name}",
            )
        else:
            logger.info("%s grew on %s that was not occupied", player.name, tile.for_human())
            new_occupied_tile = OccupiedTile.objects.create(
                game=game,
                col=tile.col,
                row=tile.row,
                player_in_game=player_in_game,
                level=(tile_level := game.config.tile_start_level * action.efficiency + tile_dist_compensation),
            )
            # noinspection InvisibleCharacter
            add_message(
                player_in_game,
                f"{player_in_game.player.name} s'est agrandi en {tile.for_human()} ({tile_level:.2f} PV)",
            )
            for drop_event in game.randomevent_set.filter(
                event_type=RandomEventType.DROP_ACTIONS,
                drop_picked_up=False,
                tile_col=tile.col,
                tile_row=tile.row,
            ):
                if drop_event.apply_drop(new_occupied_tile) is None:
                    logger.warning("Drop couldn't be picked up by %s on %s", player.name, tile.for_human())
                else:
                    logger.info(
                        "%s picked up drop of %s on %s",
                        player_in_game.player.name,
                        drop_event.drop_actions_amount,
                        tile.for_human(),
                    )
                    add_message(
                        player_in_game,
                        f"{player_in_game.player.name} a récupéré {drop_event.drop_actions_amount} points d'actions "
                        f"en {tile.for_human()} suite a un ancien drop",
                    )

        if not player_in_game.nb_tiles:
            messages.append(
                GameMessage(
                    text=f"{player_in_game.player.name} "
                    f"{'commence' if player_in_game.first_in_game_for_player else 'revient'} "
                    f"en {tile.for_human()}",
                    kind=GameMessageKind.SPAWN,
                    color=player_in_game.color_object,
                    player_id=player.id,
                    chat_text=None
                    if player.welcome_chat_message_sent_at
                    else (
                        f"Bienvenue dans la partie @{player_in_game.player.name} ! "
                        f"Tu commences en {tile.for_human()} ! "
                        "Tu vas bientôt pouvoir t'agrandir, te défendre ou attaquer !"
                    )
                    if game.config.multi_steps
                    else (
                        f"Bienvenue dans la partie @{player_in_game.player.name} ! "
                        f"Tu vas apparaître en {tile.for_human()} dans quelques secondes ! "
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


def compute_start_banked_actions(game: Game, mininum: float) -> float:
    """Compute the number of banked actions for a player entering the game."""
    return max(
        mininum,
        (
            game.get_all_players_in_games()
            .annotate(nb_tiles=Count("occupiedtile"))
            .filter(nb_tiles__gt=0)
            .aggregate(Avg("nb_tiles"))["nb_tiles__avg"]
            or 0
        ),
    )


async def aplay_turn(
    game: Game,
    grid: Grid,
    turn: Optional[int] = None,
    send_messages: Optional[Callable[[list[GameMessage]], Coroutine[Any, Any, None]]] = None,
) -> GameMessages:
    """Play a turn and send message or return them."""
    turn = game.current_turn if turn is None else turn
    actions = await sync_to_async(lambda: list(game.confirmed_actions_for_turn(turn).order_by("confirmed_at")))()
    logger_execute.info("Playing turn %s: %s actions", turn, len(actions))
    dead_during_turn: set[int] = set()
    if game.config.multi_steps:
        dead_during_turn = await sync_to_async(
            lambda: set(game.playeringame_set.filter(ended_turn=turn).values_list("id", flat=True))
        )()
    nb_actions: dict[int, int] = defaultdict(int)
    all_messages: GameMessages = []
    for action in actions:
        if messages := await sync_to_async(execute_action)(action, game, grid, turn, nb_actions, dead_during_turn):
            if send_messages is not None:
                await send_messages(messages)
                if game.config.multi_steps:
                    await asyncio.sleep(game.config.message_delay.total_seconds() * len(messages))
            else:
                all_messages.extend(messages)

    if game.config.multi_steps:
        await PlayerInGame.aupdate_all_banked_actions(nb_actions)
        await update_levels(game)

    return all_messages


async def update_levels(game: Game) -> GameMessages:
    """Update levels of all players."""
    if not game.config.multi_steps:
        return []

    all_messages: GameMessages = []
    updated_levels = await PlayerInGame.aupdate_all_levels(game)
    for player_in_game, (old_level, new_level) in updated_levels.items():
        all_messages.append(
            GameMessage(
                text=f"{player_in_game.player.name} avance level {new_level}"
                if new_level > old_level
                else f"{player_in_game.player.name} rétrograde level {new_level}",
                kind=GameMessageKind.LEVEL_UPDATED,
                color=player_in_game.color_object,
                player_id=player_in_game.player_id,
            )
        )

    return all_messages


def get_free_color(game: Game, default: Color) -> Color:
    """Get a color not already used in the game, using the default if not used, or no other available."""
    used_colors = {pig.color_object for pig in game.get_current_players_in_game()}
    if default not in used_colors:
        return default
    free_colors = set(PALETTE) - used_colors
    return free_colors.pop() if free_colors else default


def get_or_create_player_in_game(
    player: Player, game: Game, allow_new: bool, allow_existing: bool
) -> Optional[PlayerInGame]:
    """Get the player in game, or create it if not existing."""
    player_in_game = (
        game.playeringame_set.filter(
            player=player,
        )
        .order_by("-id")
        .first()
    )

    if player_in_game is not None and player_in_game.ended_turn is None:
        return player_in_game if allow_existing else None

    if not allow_new:
        return None

    if game.get_current_players_in_game().count() >= game.config.max_players:
        logger_new_players.warning("%s tried to join but the game is full", player.name)
        return None

    if player_in_game is not None and not player_in_game.can_respawn():
        logger_new_players.warning("%s is still dead", player.name)
        return None

    logger_new_players.warning("%s is a %s player", player.name, "NEW" if player_in_game is None else "returning")
    return PlayerInGame.objects.create(
        player=player,
        game=game,
        color=get_free_color(game, PALETTE[player.id % NB_COLORS]).as_hex,
        first_in_game_for_player=player_in_game is None
        or (player_in_game.first_in_game_for_player and player_in_game.start_tile_col is None),
        started_turn=game.current_turn,
        level=game.config.player_start_level,
        # in multi steps mode, an action is created on user arrival, we need to let the user play in the actions step
        banked_actions=compute_start_banked_actions(game, 1) if game.config.multi_steps else 0,
    )


def can_create_action(player_in_game: PlayerInGame) -> bool:
    """Check if the player can create an action."""
    if not player_in_game.can_create_action():
        logger_collect.warning("%s has no action left", player_in_game.player.name)
        return False
    return True


def get_current_action(player_in_game: PlayerInGame, game: Game) -> Optional[Action]:
    """Get the current action of a player in game."""
    return (
        player_in_game.action_set.filter(
            turn=game.current_turn,
            state=ActionState.CREATED,
        )
        .order_by("-id")
        .first()
    )


def set_action_tile(
    player_in_game: PlayerInGame, game: Game, tile: Tile, action: Optional[Action] = None
) -> Optional[Action]:
    """Set the tile of the action currently being created."""
    if action is None:
        action = get_current_action(player_in_game, game)
    if action is None:
        logger_collect.warning("%s has no current action", player_in_game.player.name)
        return None
    if action.action_type == ActionType.BANK:
        logger_collect.warning(
            "%s has a %s action so cannot set a tile", player_in_game.player.name, ActionType(action.action_type).name
        )
        return None
    action.set_tile(tile)
    logger_collect.info(
        "%s set tile %s for action %s",
        player_in_game.player.name,
        tile.for_human(),
        ActionType(action.action_type).name,
    )
    return action


def create_or_update_action(player_in_game: PlayerInGame, game: Game, action_type: ActionType) -> Optional[Action]:
    """Create or update an action for a player in game."""
    if player_in_game.start_tile_col is None and action_type != ActionType.GROW:
        logger_collect.warning(
            "%s cannot %s as a %s player",
            player_in_game.player.name,
            ActionType(action_type).name,
            "new" if player_in_game.first_in_game_for_player else "returning",
        )
        return None
    action = get_current_action(player_in_game, game)
    if action is not None:
        action.action_type = action_type
        action.set_tile(None, save=False)
        action.save()
        logger_collect.info("%s updated its action to a %s action", player_in_game.player.name, action_type.name)
        return action
    logger_collect.info("%s created a %s action", player_in_game.player.name, action_type.name)
    return Action.objects.create(
        player_in_game=player_in_game,
        game=game,
        turn=game.current_turn,
        action_type=action_type,
        state=ActionState.CREATED,
    )


def confirm_action(
    player_in_game: PlayerInGame, game: Game, efficiency: float = 1.0, action: Optional[Action] = None
) -> Optional[Action]:
    """Confirm the current action of a player in game."""
    if action is None:
        action = get_current_action(player_in_game, game)
    if action is None:
        logger_collect.warning("%s has no current action", player_in_game.player.name)
        return None
    if action.action_type != ActionType.BANK and not action.is_tile_set():
        logger_collect.warning(
            "%s has no tile set for its current %s action",
            player_in_game.player.name,
            ActionType(action.action_type).name,
        )
        return None
    action.confirm(efficiency)
    if action.action_type == ActionType.BANK:
        logger_collect.info(
            "%s confirmed its %s action", player_in_game.player.name, ActionType(action.action_type).name
        )
    else:
        logger_collect.info(
            "%s confirmed its %s action on %s",
            player_in_game.player.name,
            ActionType(action.action_type).name,
            action_tile.for_human() if (action_tile := action.tile) is not None else None,
        )
    return action


def erode_map(game: Game, grid: Grid) -> tuple[list[PlayerInGame], GameMessages]:
    """Erode borders of players maps."""
    if not game.config.multi_steps:
        return [], []

    messages: GameMessages = []
    dead_players: list[PlayerInGame] = []

    def add_message(
        player_in_game: PlayerInGame,
        text: str,
        kind: GameMessageKind = GameMessageKind.EROSION,
    ) -> None:
        messages.append(
            GameMessage(text, kind=kind, color=player_in_game.color_object, player_id=player_in_game.player_id)
        )

    players_in_game = game.get_current_players_in_game_with_occupied_tiles()
    for player_in_game in players_in_game:
        occupied_tiles = list(player_in_game.occupiedtile_set.all())
        nb_tiles = len(occupied_tiles)
        border_tiles = grid.get_border_tiles({occupied_tile.tile for occupied_tile in occupied_tiles})
        is_active = player_in_game.is_active()
        for occupied_tile in occupied_tiles:
            try:
                damage = (EROSION_DAMAGES_ACTIVE_PLAYER if is_active else EROSION_DAMAGES_INACTIVE_PLAYER) * len(
                    border_tiles[tile := occupied_tile.tile]
                )
            except KeyError:
                continue
            occupied_tile.level -= damage
            if occupied_tile.level > 0:
                occupied_tile.save()
                continue
            occupied_tile.delete()
            logger_erosion.info("Erosion destroyed tile %s from %s", tile.for_human(), player_in_game.player.name)
            add_message(
                player_in_game,
                f"{player_in_game.player.name} a perdu {tile.for_human()} à cause de l'érosion",
            )
            nb_tiles -= 1

        if nb_tiles <= 0:
            logger_erosion.warning("%s IS NOW DEAD", player_in_game.player.name)
            player_in_game.die(turn=game.current_turn)
            add_message(
                player_in_game,
                f"{player_in_game.player.name} a disparu de la carte, érodé jusqu'à l'os",
                GameMessageKind.DEATH,
            )
            dead_players.append(player_in_game)

    return dead_players, messages


def run_random_events(  # pylint: disable=too-many-branches, too-many-statements
    game: Game, grid: Grid, random_event: Optional[RandomEvent] = None
) -> tuple[list[PlayerInGame], GameMessages]:
    """Create a random event."""
    if not game.config.multi_steps:
        return [], []

    messages: GameMessages = []
    dead_players: list[PlayerInGame] = []

    def add_anonymous_message(text: str) -> None:
        messages.append(GameMessage(text, kind=GameMessageKind.RANDOM_EVENT, color=Color(255, 255, 255)))

    if random_event is None and (random_event := RandomEvent.generate_event(game)) is None:
        add_anonymous_message(choice(NO_EVENT_MESSAGES))
        return dead_players, messages

    def add_message(
        player_in_game: PlayerInGame,
        text: str,
        kind: GameMessageKind = GameMessageKind.RANDOM_EVENT,
    ) -> None:
        messages.append(
            GameMessage(text, kind=kind, color=player_in_game.color_object, player_id=player_in_game.player_id)
        )

    if random_event.event_type == RandomEventType.LIGHTNING:
        logger_events.info(
            "Random event: lightning in %s, damage: %s",
            random_event.tile.for_human(),
            random_event.lightning_damage,
        )
        player_in_game, tile_destroyed = random_event.apply_lightning()
        if player_in_game is None:
            logger_events.info("Lightning with no effect")
            add_anonymous_message(
                f"Un éclair de force {random_event.lightning_damage} "
                f"a frappé en {random_event.tile.for_human()} sans faire de dégats.",
            )
        else:
            if tile_destroyed:
                logger_events.info("Lightning destroyed %s tile", player_in_game.player.name)
                add_message(
                    player_in_game,
                    f"{player_in_game.player.name} a perdu {random_event.tile.for_human()} "
                    f"suite à un éclair de force {random_event.lightning_damage}",
                )
                if not player_in_game.count_tiles():
                    logger_events.warning("%s IS NOW DEAD", player_in_game.player.name)
                    player_in_game.die(turn=game.current_turn)
                    add_message(
                        player_in_game,
                        f"{player_in_game.player.name} a disparu de la carte, terrassé par cet éclair",
                        GameMessageKind.DEATH,
                    )
                    dead_players.append(player_in_game)
            else:
                logger_events.info("Lightning touched %s tile", player_in_game.player.name)
                add_message(
                    player_in_game,
                    f"{player_in_game.player.name} a reçu un éclair de force {random_event.lightning_damage} "
                    f"en {random_event.tile.for_human()}",
                )

    elif random_event.event_type == RandomEventType.EARTHQUAKE:
        logger_events.info(
            "Random event: earthquake in %s, damage: %s, radius: %s",
            random_event.tile.for_human(),
            random_event.earthquake_damage,
            random_event.earthquake_radius,
        )
        touched_players_in_game = random_event.apply_earthquake(grid)
        if touched_players_in_game:
            add_anonymous_message(
                f"Un tremblement de terre de force {random_event.earthquake_damage} "
                f"et rayon {random_event.earthquake_radius} a frappé en {random_event.tile.for_human()}",
            )
        else:
            logger_events.info("Earthquake with no effect")
            add_anonymous_message(
                f"Un tremblement de terre de force {random_event.earthquake_damage} "
                f"et rayon {random_event.earthquake_radius} a frappé en {random_event.tile.for_human()} "
                f"sans faire de dégats.",
            )
        for player_in_game, (nb_tiles, nb_destroyed_tiles) in touched_players_in_game.items():
            nb_touched_tiles = nb_tiles - nb_destroyed_tiles
            logger_events.info(
                "Earthquake on %s: %s touched, %s destroyed",
                player_in_game.player.name,
                nb_touched_tiles,
                nb_destroyed_tiles,
            )
            if nb_touched_tiles and nb_destroyed_tiles:
                add_message(
                    player_in_game,
                    f"{player_in_game.player.name} a eu "
                    f"{nb_touched_tiles} cases touchée{'s' if nb_touched_tiles > 1 else ''}"
                    f" et {nb_destroyed_tiles} détruite{'s' if nb_destroyed_tiles > 1 else ''}",
                )
            elif nb_touched_tiles:
                add_message(
                    player_in_game,
                    f"{player_in_game.player.name} a eu "
                    f"{nb_touched_tiles} cases touchée{'s' if nb_touched_tiles > 1 else ''}",
                )
            else:
                add_message(
                    player_in_game,
                    f"{player_in_game.player.name} a eu "
                    f"{nb_destroyed_tiles} case détruite{'s' if nb_destroyed_tiles > 1 else ''}",
                )
            if not player_in_game.count_tiles():
                logger_events.warning("%s IS NOW DEAD", player_in_game.player.name)
                player_in_game.die(turn=game.current_turn)
                add_message(
                    player_in_game,
                    f"{player_in_game.player.name} a disparu de la carte, terrassé par ce tremblement de terre",
                    GameMessageKind.DEATH,
                )
                dead_players.append(player_in_game)

    elif random_event.event_type == RandomEventType.DROP_ACTIONS:
        logger_events.info(
            "Random event: drop in %s, amount: %s",
            random_event.tile.for_human(),
            random_event.drop_actions_amount,
        )
        if (player_in_game := random_event.apply_drop()) is None:
            logger_events.info("Drop with no effect")
            add_anonymous_message(f"Un drop de points d'actions a eu lieu en {random_event.tile.for_human()}.")
        else:
            logger_events.info("Drop on %s tile", player_in_game.player.name)
            add_message(
                player_in_game,
                f"{player_in_game.player.name} a récupéré {random_event.drop_actions_amount} points d'actions "
                f"suite a un drop en {random_event.tile.for_human()}",
            )

    return dead_players, messages


async def on_click(  # pylint: disable=unused-argument
    player: Player,
    x_relative: float,
    y_relative: float,
    game: Game,
    grid: ConcreteGrid,
    clicks_queue: ClicksQueue,
    clicks_allowed_event: asyncio.Event,
) -> None:
    """Display a message when a click is received."""
    if not clicks_allowed_event.is_set():
        return
    target, point = get_click_target(x_relative, y_relative)
    if target == ClickTarget.MAP:
        area = COORDINATES[target]
        tile = grid.get_tile_at_point(Point(x=point.x - area[0][0], y=point.y - area[0][1]))
        await clicks_queue.put(PlayerClick(player, target, tile))
    elif target is not None:
        await clicks_queue.put(PlayerClick(player, target, None))


def get_game_and_grid(game_mode: GameMode) -> tuple[Game, ConcreteGrid]:
    """Get the current game."""
    area = COORDINATES[ClickTarget.MAP]
    width = area[1][0] - area[0][0]
    height = area[1][1] - area[0][1]
    game, tile_size = Game.get_current(game_mode, 500, width, height)
    grid = ConcreteGrid(Grid(game.grid_nb_cols, game.grid_nb_rows), tile_size)
    return game, grid
