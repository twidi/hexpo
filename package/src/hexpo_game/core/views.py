"""Views for the hexpo_game.core app."""

import django
from aiohttp import web
from aiohttp.web import Response
from django.template import loader

django.setup()


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
    html = loader.render_to_string("core/index.html")
    return Response(text=html, content_type="text/html")


def add_routes(router: web.UrlDispatcher) -> None:
    """Add routes to the router."""
    router.add_get("/", index)
    # router.add_get('/sse', sse)


if __name__ == "__main__":
    app = web.Application()
    add_routes(app.router)
    web.run_app(app, host="127.0.0.1", port=8000)
