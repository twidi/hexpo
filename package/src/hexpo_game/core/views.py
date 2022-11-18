"""Views for the hexpo_game.core app."""

from aiohttp import web
from aiohttp.web import Response
from asgiref.sync import sync_to_async
from django.template import loader

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import
from .game import get_game_and_grid
from .models import Player
from .types import Color, Tile


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
async def index(request: web.Request) -> web.Response:  # pylint: disable=unused-argument
    """Display the index page."""
    game, grid = await sync_to_async(get_game_and_grid)()

    grid.draw_map_contour(Color(0, 0, 0))

    def get_players_in_game() -> list[Player]:
        return list(game.playeringame_set.select_related("player").prefetch_related("player__occupiedtile_set").all())

    for player_in_game in await sync_to_async(get_players_in_game)():
        grid.draw_areas(
            (
                Tile(occupied_tile.col, occupied_tile.row)
                for occupied_tile in player_in_game.player.occupiedtile_set.all()
            ),
            Color.from_hex(player_in_game.color),
        )

    context = {
        "grid_base64": grid.map_as_base64_png(),
    }

    html = loader.render_to_string("core/index.html", context)
    return Response(text=html, content_type="text/html")


def add_routes(router: web.UrlDispatcher) -> None:
    """Add routes to the router."""
    router.add_get("/", index)
    # router.add_get('/sse', sse)


if __name__ == "__main__":
    app = web.Application()
    add_routes(app.router)
    web.run_app(app, host="127.0.0.1", port=8000)
