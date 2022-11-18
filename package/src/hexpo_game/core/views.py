"""Views for the hexpo_game.core app."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, cast

from aiohttp import web
from aiohttp.web import Response
from asgiref.sync import sync_to_async
from django.db.models import Count, Max, Q
from django.template import loader

from hexpo_game.core.grid import ConcreteGrid

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .game import get_game_and_grid
from .models import Game, PlayerInGame
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

    def get_game_last_updated(self) -> Optional[datetime]:
        """Get the last updated time of the game, i.e. the date of the last updated tile."""
        return cast(
            Optional[datetime],
            (
                self.game.occupiedtile_set.all()
                .exclude(updated_at__isnull=True)
                .aggregate(max_last_updated=Max("updated_at"))["max_last_updated"]
            ),
        )

    async def draw_grid(self) -> bool:
        """Redraw the grid."""
        max_last_updated = await sync_to_async(self.get_game_last_updated)()
        if max_last_updated is not None and max_last_updated > self.last_updated:
            self.last_updated = max_last_updated
        else:
            return False

        self.grid.reset_map()
        self.grid.draw_map_contour(Color(0, 0, 0))

        def get_players_in_game() -> list[PlayerInGame]:
            return list(
                self.game.playeringame_set.select_related("player").prefetch_related("player__occupiedtile_set").all()
            )

        for player_in_game in await sync_to_async(get_players_in_game)():
            self.grid.draw_areas(
                (
                    Tile(occupied_tile.col, occupied_tile.row)
                    for occupied_tile in player_in_game.player.occupiedtile_set.all()
                ),
                Color.from_hex(player_in_game.color).as_bgr(),
            )

        return True

    def get_players_context(self) -> list[dict[str, Any]]:
        """Get the context for the players left bar."""
        players_in_game = (
            self.game.playeringame_set.all()
            .select_related("player")
            .annotate(nb_tiles=Count("player__occupiedtile", filter=Q(player__occupiedtile__game=self.game)))
            .order_by("-nb_tiles", "-id")[:20]
        )
        return [
            {
                "name": player_in_game.player.name,
                "color": player_in_game.color,
                "rank": index,
                "nb_tiles": player_in_game.nb_tiles,
                "percent_tiles": f"{player_in_game.nb_tiles / self.grid.nb_tiles * 100:.2f}",
                "id": player_in_game.id,
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
