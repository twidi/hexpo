"""Views for the hexpo_game.core app."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiohttp import web
from aiohttp.web import Response
from asgiref.sync import sync_to_async
from django.template import loader
from django.utils import timezone

from hexpo_game.core.constants import RESPAWN_FORBID_DURATION
from hexpo_game.core.grid import ConcreteGrid

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .game import get_game_and_grid
from .models import Game
from .types import Color, Tile

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

    @classmethod
    def load_from_db(cls) -> GameState:
        """Load the game state from the database."""
        game, grid = get_game_and_grid()
        return cls(game=game, grid=grid, last_updated=game.started_at)

    async def draw_grid(self) -> bool:
        """Redraw the grid."""
        max_last_updated = await sync_to_async(self.game.get_last_tile_update_at)()
        if max_last_updated is not None and max_last_updated > self.last_updated:
            self.last_updated = max_last_updated
        else:
            return False

        self.grid.reset_map()
        self.grid.draw_map_contour(Color(0, 0, 0))

        now = timezone.now()
        for player_in_game in await sync_to_async(self.game.get_players_in_game_with_occupied_tiles)():
            self.grid.draw_areas(
                (
                    Tile(occupied_tile.col, occupied_tile.row)
                    for occupied_tile in player_in_game.occupiedtile_set.all()
                ),
                Color.from_hex(player_in_game.color).as_bgr(),
                mark=player_in_game.is_protected(now),
            )

        return True

    def get_players_context(self) -> list[dict[str, Any]]:
        """Get the context for the players left bar."""
        players_in_game = self.game.get_players_in_game_for_leader_board(15)
        now = timezone.now()
        alive_time = now - RESPAWN_FORBID_DURATION

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
                "can_play": not player_in_game.dead_at or player_in_game.dead_at < alive_time,
                "is_protected": player_in_game.is_protected(now),
            }
            for index, player_in_game in enumerate(players_in_game, 1)
        ]

    async def http_get_players(self, request: web.Request) -> web.Response:
        """Return the players partial html."""
        context = {"players": await sync_to_async(self.get_players_context)()}
        html = loader.render_to_string("core/include_players.html", context)
        return Response(text=html, content_type="text/html")

    async def http_get_index(self, request: web.Request) -> web.Response:  # pylint: disable=unused-argument
        """Display the index page."""
        await self.draw_grid()
        context = {
            "grid_base64": self.grid.map_as_base64_png(),
            "players": await sync_to_async(self.get_players_context)(),
        }

        html = loader.render_to_string("core/index.html", context)
        return Response(text=html, content_type="text/html")

    async def http_get_grid_base64(self, request: web.Request) -> web.Response:
        """Return the base64 encoded grid as a plain text response."""
        grid_updated = await self.draw_grid()
        if grid_updated:
            return Response(text=self.grid.map_as_base64_png(), content_type="text/plain")
        return Response(status=304)


def add_routes(router: web.UrlDispatcher) -> None:
    """Add routes to the router."""
    game_state = GameState.load_from_db()
    router.add_get("/", game_state.http_get_index)
    router.add_get("/grid", game_state.http_get_grid_base64)
    router.add_get("/players", game_state.http_get_players)
    # router.add_get('/sse', sse)


if __name__ == "__main__":
    app = web.Application()
    add_routes(app.router)
    web.run_app(app, host="127.0.0.1", port=8000)
