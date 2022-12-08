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
from .constants import ClickTarget
from .game import get_game_and_grid
from .grid import ConcreteGrid
from .models import Game, PlayerInGame
from .types import Color, GameMessage, GameMessagesQueue, Tile

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


@dataclass
class GameState:
    """The state of the current running game."""

    game: Game
    grid: ConcreteGrid
    last_updated: datetime

    def __post_init__(self) -> None:
        """Get the last players and prepare the list of messages."""
        self.messages: list[GameMessage] = []

    @classmethod
    def load_from_db(cls) -> GameState:
        """Load the game state from the database."""
        game, grid = get_game_and_grid()
        return cls(game=game, grid=grid, last_updated=game.started_at)

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
                message = await asyncio.wait_for(queue.get(), timeout=1)
            except asyncio.TimeoutError:
                continue
            else:
                self.messages.append(message)
                queue.task_done()

    async def draw_grid(self) -> bool:
        """Redraw the grid."""
        max_last_updated = await sync_to_async(self.game.get_last_tile_update_at)()
        if max_last_updated is not None and max_last_updated > self.last_updated:
            self.last_updated = max_last_updated
        else:
            return False

        self.grid.reset_map()
        self.grid.draw_map_contour(Color(0, 0, 0))

        for player_in_game in await sync_to_async(self.game.get_current_players_in_game_with_occupied_tiles)():
            self.grid.draw_areas(
                (
                    Tile(occupied_tile.col, occupied_tile.row)
                    for occupied_tile in player_in_game.occupiedtile_set.all()
                ),
                player_in_game.color_object.as_bgr(),
                mark=player_in_game.is_protected(),
            )

        return True

    def get_players_context(self) -> list[dict[str, Any]]:
        """Get the context for the players left bar."""
        players_in_game = self.game.get_players_in_game_for_leader_board(15)

        return [
            {
                "name": player_in_game.player.name,
                "color": player_in_game.color,
                "rank": index,
                "nb_tiles": player_in_game.nb_tiles,  # type: ignore[attr-defined]
                "percent_tiles": f"{player_in_game.nb_tiles / self.grid.nb_tiles * 100:.1f}%"  # type: ignore[attr-defined]  # pylint: disable=line-too-long
                if player_in_game.nb_tiles  # type: ignore[attr-defined]
                else "",
                "nb_actions": player_in_game.nb_actions,  # type: ignore[attr-defined]
                "nb_games": player_in_game.nb_games,  # type: ignore[attr-defined]
                "nb_kills": player_in_game.nb_kills,  # type: ignore[attr-defined]
                "can_play": player_in_game.ended_turn is None or player_in_game.can_respawn(),  # type: ignore
                "is_protected": player_in_game.is_protected(),
            }
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
        context = {"players": await sync_to_async(self.get_players_context)()}
        html = loader.render_to_string("core/include_players.html", context)
        return Response(text=html, content_type="text/html")

    async def http_get_players(self, request: web.Request) -> web.Response:
        """Return the players partial html."""
        context = {
            "players": await sync_to_async(self.get_players_context)(),
            "timestamp": time(),
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
        }

        html = loader.render_to_string("core/index.html", context)
        return Response(text=html, content_type="text/html")

    async def http_get_grid_base64(self, request: web.Request) -> web.Response:
        """Return the base64 encoded grid as a plain text response."""
        grid_updated = await self.draw_grid()
        if grid_updated:
            return Response(text=self.grid.map_as_base64_png(), content_type="text/plain")
        return Response(status=304)


def prepare_views(router: web.UrlDispatcher) -> GameState:
    """Prepare the game state and add the views to the router."""
    game_state = GameState.load_from_db()
    router.add_get("/", game_state.http_get_index)
    router.add_get("/grid.raw", game_state.http_get_grid_base64)
    router.add_get("/players.partial", game_state.http_get_players_partial)
    router.add_get("/players", game_state.http_get_players)
    router.add_get("/messages.partial", game_state.http_get_messages_partial)
    router.add_static("/statics", Path(__file__).parent / "statics")
    # router.add_get('/sse', sse)
    return game_state
