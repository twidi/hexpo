"""Views for the hexpo_game.core app."""

from aiohttp import web
from aiohttp.web import Response
from django.template import loader

from hexpo_game.core.click_handler import COORDINATES
from hexpo_game.core.grid import Color, ConcreteGrid, Grid

from .. import django_setup  # noqa: F401  # pylint: disable=unused-import


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
    area = COORDINATES["grid-area"]
    width = area[1][0] - area[0][0]
    height = area[1][1] - area[0][1]
    nb_cols, nb_rows, tile_size = ConcreteGrid.compute_grid_size(1000, width, height)
    grid = ConcreteGrid(Grid(nb_cols, nb_rows), tile_size)

    for tile in grid:
        color = Color.random()
        grid.fill_tiles([tile.tile], color)

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
