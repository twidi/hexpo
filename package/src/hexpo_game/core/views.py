"""Views for the hexpo_game.core app."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from string import ascii_letters
from time import time
from typing import Any

from aiohttp import web
from aiohttp.web import Response
from asgiref.sync import sync_to_async
from django.db.models import Count
from django.template import loader

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .click_handler import COORDINATES
from .constants import ActionState, ActionType, ClickTarget, GameEndMode, GameStep
from .grid import ConcreteGrid
from .models import Action, Game, PlayerInGame
from .types import Color, DrawTileMode, GameMessage, GameMessagesQueue, Tile

logger = logging.getLogger(__name__)

# async def sse(request):
#     async with sse_response(request) as resp:
#         while True:
#             data = 'Server Time : {}'.format(datetime.now())
#             print(data)
#             await resp.send(data)
#             await asyncio.sleep(1)
#     return resp
#
#


def int_or_float_as_str(value: float) -> str:
    """Return the string representation of a float or an int."""
    return str(int(value)) if value.is_integer() else f"{value:.2f}"


@dataclass
class GameState:
    """The state of the current running game."""

    game: Game
    grid: ConcreteGrid
    last_updated: datetime

    def __post_init__(self) -> None:
        """Get the last players and prepare the list of messages."""
        self.messages: list[GameMessage] = []
        self.grid_state: dict[Tile, tuple[int, datetime]] = {}

    async def update_forever(self, game_messages_queue: GameMessagesQueue, delay: float) -> None:
        """Update the game state forever."""
        while True:
            await self.game.arefresh_from_db()
            await self.update_messages(game_messages_queue)
            await asyncio.sleep(delay)

    def get_new_players(self, ids: list[int]) -> list[PlayerInGame]:
        """Get the new players from the given ids."""
        return list(
            self.game.playeringame_set.filter(id__in=ids)
            .annotate(nb_pigs=Count("player__playeringame"))
            .select_related("player")
            .order_by("started_at")
        )

    def get_dead_players(self, ids: list[int]) -> list[PlayerInGame]:
        """Get the dead players from the given ids."""
        return list(
            self.game.playeringame_set.filter(id__in=ids)
            .select_related("player", "killed_by__player")
            .order_by("dead_at")
        )

    async def update_messages(self, queue: GameMessagesQueue) -> None:
        """Update the list of messages to display."""
        # pylint: disable=duplicate-code
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                break
            else:
                self.messages.append(message)
                queue.task_done()

    def get_grid_state(self) -> dict[Tile, tuple[int, datetime]]:
        """Return the grid state."""
        return {
            Tile(col, row): (player_in_game_id, updated_at)
            for col, row, player_in_game_id, updated_at in self.game.occupiedtile_set.values_list(
                "col", "row", "player_in_game_id", "updated_at"
            )
        }

    async def draw_grid(self) -> bool:
        """Redraw the grid."""
        new_grid_state = await sync_to_async(self.get_grid_state)()
        if new_grid_state == self.grid_state:
            return False

        self.grid_state = new_grid_state

        self.grid.reset_map()
        if self.game.config.multi_steps:
            self.grid.draw_areas(
                self.grid.grid.tiles_set - set(self.grid_state),
                Color(255, 255, 255),
                mode=DrawTileMode.FILL,
            )
        else:
            self.grid.draw_map_contour(Color(0, 0, 0))

        tiles_per_player_id: dict[int, list[Tile]] = {}
        for tile, (player_in_game_id, _) in self.grid_state.items():
            tiles_per_player_id.setdefault(player_in_game_id, []).append(tile)

        players_in_game = await self.game.playeringame_set.ain_bulk(tiles_per_player_id.keys())

        for player_in_game_id, tiles in tiles_per_player_id.items():
            player_in_game = players_in_game[player_in_game_id]
            self.grid.draw_areas(
                tiles,
                player_in_game.color_object.as_bgr(),
                mark=player_in_game.is_protected(len(tiles)),
            )

        return True

    def get_players_context(self) -> list[dict[str, Any]]:
        """Get the context for the players left bar."""
        players_in_game = list(
            self.game.get_players_in_game_for_leader_board(15 if self.game.config.multi_steps else 16)
        )
        actions_by_player: dict[int, list[Action]] = {}

        if self.game.config.multi_steps and self.game.current_turn_step in (
            GameStep.COLLECTING_ACTIONS,
            GameStep.RANDOM_EVENTS,
            GameStep.EXECUTING_ACTIONS,
        ):
            all_actions = self.game.action_set.filter(
                player_in_game_id__in=[player_in_game.id for player_in_game in players_in_game],
                turn=self.game.current_turn,
            )
            if self.game.current_turn_step != GameStep.COLLECTING_ACTIONS:
                all_actions = all_actions.exclude(state=ActionState.CREATED)
            for action in all_actions:
                actions_by_player.setdefault(action.player_in_game_id, []).append(action)
            for actions in actions_by_player.values():
                actions.sort(
                    key=lambda action: (1, None) if action.state == ActionState.CREATED else (0, action.confirmed_at)
                )

        return [
            {
                "name": player_in_game.player.name,
                "color": player_in_game.color,
                "rank": index,
                "can_play": player_in_game.ended_turn is None or player_in_game.can_respawn(),
                "is_protected": player_in_game.is_protected(),
                "nb_tiles": player_in_game.nb_tiles,  # type: ignore[attr-defined]
                "next_respawn_turn": player_in_game.next_respawn_turn if player_in_game.ended_turn else None,
            }
            | (
                {
                    "level": player_in_game.level,
                    "current_turn_actions": (actions := actions_by_player.get(player_in_game.id, [])),
                    "level_actions_left": max(0, overflow_actions := (player_in_game.level - len(actions))),
                    "banked_actions_left": int_or_float_as_str(
                        player_in_game.banked_actions - max(0, -overflow_actions)
                    ),
                }
                if self.game.config.multi_steps
                else {
                    "percent_tiles": f"{player_in_game.nb_tiles / self.grid.nb_tiles * 100:.1f}%"  # type: ignore[attr-defined]  # pylint: disable=line-too-long
                    if player_in_game.nb_tiles  # type: ignore[attr-defined]
                    else "",
                    "nb_actions": player_in_game.nb_actions,  # type: ignore[attr-defined]
                    "nb_games": player_in_game.nb_games,  # type: ignore[attr-defined]
                    "nb_kills": player_in_game.nb_kills,  # type: ignore[attr-defined]
                }
            )
            for index, player_in_game in enumerate(players_in_game, 1)
        ]

    async def http_get_messages_partial(self, request: web.Request) -> web.Response:
        """Get the messages partial."""
        context = {"messages": self.messages}
        html = loader.render_to_string("core/include_messages.html", context)
        self.messages.clear()
        return Response(text=html, content_type="text/html")

    async def http_get_players_partial(self, request: web.Request) -> web.Response:
        """Return the players partial html."""
        context = {
            "game": self.game,
            "players": await sync_to_async(self.get_players_context)(),
            "ActionType": ActionType,
            "ActionState": ActionState,
        }
        html = loader.render_to_string("core/include_players.html", context)
        return Response(text=html, content_type="text/html")

    async def http_get_step_partial(self, request: web.Request) -> web.Response:
        """Return the step partial html."""
        context = {
            "game": self.game,
            "GameStep": GameStep,
            "GameEndMode": GameEndMode,
        }
        html = loader.render_to_string("core/include_step_and_instructions_fragment.html", context)
        return Response(text=html, content_type="text/html")

    async def http_get_players(self, request: web.Request) -> web.Response:
        """Return the players partial html."""
        context = {
            "game": self.game,
            "players": await sync_to_async(self.get_players_context)(),
            "timestamp": time(),
            "ActionType": ActionType,
            "ActionState": ActionState,
            "reload": request.rel_url.query.get("reload", "true") != "false",
        }
        html = loader.render_to_string("core/players.html", context)
        return Response(text=html, content_type="text/html")

    async def http_get_index(self, request: web.Request) -> web.Response:  # pylint: disable=unused-argument
        """Display the index page."""
        await self.draw_grid()
        context = {
            "grid_base64": self.grid.map_as_base64_png(),
            "players": await sync_to_async(self.get_players_context)(),
            "messages": self.messages,
            "timestamp": time(),
            "reload": request.rel_url.query.get("reload", "true") != "false",
            "map_width": int(self.grid.map_size.x),
            "map_height": int(self.grid.map_size.y),
            "map_margin_right": COORDINATES[ClickTarget.MAP][1][0]
            - COORDINATES[ClickTarget.MAP][0][0]
            - int(self.grid.map_size.x),
            "map_margin_bottom": COORDINATES[ClickTarget.MAP][1][1]
            - COORDINATES[ClickTarget.MAP][0][1]
            - int(self.grid.map_size.y),
            "tile_width": self.grid.tile_width,
            "tile_height": self.grid.tile_height,
            "coordinates_horizontal": list(range(1, self.grid.nb_cols + 1)),
            "coordinates_vertical": ascii_letters[26:][: self.grid.nb_rows],
            "game": self.game,
            "GameStep": GameStep,
            "GameEndMode": GameEndMode,
            "ActionType": ActionType,
            "ActionState": ActionState,
        }

        html = loader.render_to_string("core/index.html", context)
        return Response(text=html, content_type="text/html")

    async def http_get_grid_base64(self, request: web.Request) -> web.Response:
        """Return the base64 encoded grid as a plain text response."""
        grid_updated = await self.draw_grid()
        if grid_updated:
            return Response(text=self.grid.map_as_base64_png(), content_type="text/plain")
        return Response(status=304)


def prepare_views(game: Game, grid: ConcreteGrid, router: web.UrlDispatcher) -> GameState:
    """Prepare the game state and add the views to the router."""
    game_state = GameState(game, grid, game.started_at)
    router.add_get("/", game_state.http_get_index)
    router.add_get("/grid.raw", game_state.http_get_grid_base64)
    router.add_get("/players.partial", game_state.http_get_players_partial)
    router.add_get("/players", game_state.http_get_players)
    router.add_get("/messages.partial", game_state.http_get_messages_partial)
    router.add_get("/step.partial", game_state.http_get_step_partial)
    router.add_static("/statics", Path(__file__).parent / "statics")
    # router.add_get('/sse', sse)
    return game_state
