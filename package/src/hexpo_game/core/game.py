"""Main game loop and functions."""

import asyncio
import logging
from asyncio import Queue
from datetime import timedelta
from string import ascii_letters
from typing import NamedTuple, Optional, TypeAlias, cast

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
    ButtonToAction,
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
        if not self.game.config.multi_steps or await self.game.occupiedtile_set.acount() == self.grid.nb_tiles:
            return
        end_step_at = timezone.now() + self.waiting_for_players_duration
        while True:
            if self.end_step_event.is_set() or self.end_loop_event.is_set():
                break
            if timezone.now() >= end_step_at:
                break
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
        messages = play_turn(game, grid)
        action.refresh_from_db()
        if action.state == ActionState.FAILURE:
            player_in_game.die()
        return messages

    async def step_collecting_actions(self) -> None:  # pylint: disable=too-many-branches
        """Collect actions from players."""
        end_step_at = timezone.now() + self.collecting_actions_duration
        while True:
            if self.end_step_event.is_set() or self.end_loop_event.is_set():
                break
            if timezone.now() >= end_step_at and (
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
                    if self.game.config.multi_steps:
                        await sync_to_async(self.step_collecting_actions_handle_click_multi_steps)(
                            player_click, self.game
                        )
                    else:
                        await sync_to_async(self.step_collecting_actions_handle_click_single_step)(
                            player_click, self.game
                        )
                except Exception:  # pylint:disable=broad-except
                    logger.exception("Error while processing click for %s", player_click.player.name)
                self.clicks_queue.task_done()

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
                            "Tu vas bientôt pouvoir t'aggrandir, te défendre ou attaquer !"
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
        logger.warning("%s tried to join but the game is full", player.name)
        return None

    if player_in_game is not None and not player_in_game.can_respawn():
        logger_save_action.warning("%s is still dead", player.name)
        return None

    logger.warning("%s is a %s player", player.name, "NEW" if player_in_game is None else "returning")
    return PlayerInGame.objects.create(
        player=player,
        game=game,
        color=get_free_color(game, PALETTE[player.id % NB_COLORS]).as_hex,
        first_in_game_for_player=player_in_game is None
        or (player_in_game.first_in_game_for_player and player_in_game.start_tile_col is None),
        started_turn=game.current_turn,
        level=game.config.player_start_level,
    )


def can_create_action(player_in_game: PlayerInGame) -> bool:
    """Check if the player can create an action."""
    if not player_in_game.can_create_action():
        logger_save_action.warning("%s has no action left", player_in_game.player.name)
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
        logger.warning("%s has no current action", player_in_game.player.name)
        return None
    if action.action_type == ActionType.BANK:
        logger.warning(
            "%s has a %s action so cannot set a tile", player_in_game.player.name, ActionType(action.action_type).name
        )
        return None
    action.set_tile(tile)
    logger.info("%s set tile %s for action %s", player_in_game.player.name, tile, ActionType(action.action_type).name)
    return action


def create_or_update_action(player_in_game: PlayerInGame, game: Game, action_type: ActionType) -> Optional[Action]:
    """Create or update an action for a player in game."""
    if player_in_game.start_tile_col is None and action_type != ActionType.GROW:
        logger_save_action.warning(
            "%s cannot %s as a %s player",
            player_in_game.player.name,
            ActionType(action_type).name,
            "new" if player_in_game.first_in_game_for_player else "returning",
        )
        return None
    action = get_current_action(player_in_game, game)
    if action is not None:
        action.set_tile(None)
        action.action_type = action_type
        logger.info("%s updated its action to a %s action", player_in_game.player.name, action_type.name)
        return action
    logger.info("%s created a %s action", player_in_game.player.name, action_type.name)
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
        logger.warning("%s has no current action", player_in_game.player.name)
        return None
    if action.action_type != ActionType.BANK and not action.is_tile_set():
        logger.warning(
            "%s has no tile set for its current %s action",
            player_in_game.player.name,
            ActionType(action.action_type).name,
        )
        return None
    action.confirm(efficiency)
    if action.action_type == ActionType.BANK:
        logger.info("%s confirmed its %s action", player_in_game.player.name, ActionType(action.action_type).name)
    else:
        logger.info(
            "%s confirmed its %s action on %s",
            player_in_game.player.name,
            ActionType(action.action_type).name,
            action.tile,
        )
    return action


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
