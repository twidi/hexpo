"""Main entry point for the game."""
import asyncio
import logging
from asyncio import Task, ensure_future
from contextlib import suppress
from typing import Any

from aiohttp import web

from . import django_setup  # noqa: F401  # pylint: disable=unused-import
from .core.click_handler import get_click_target
from .core.clicks_providers.foofurbot import (  # noqa: E402
    catch_clicks as foofurbot_catch_clicks,
)

# pylint: disable=wrong-import-position
from .core.clicks_providers.heat import catch_clicks as heat_catch_clicks  # noqa: E402
from .core.clicks_providers.utils import get_twitch_app_token  # noqa: E402
from .core.views import add_routes  # noqa: E402

logger = logging.getLogger("hexpo_game")


# pylint: enable=wrong-import-position
def on_click(username: str, x_relative: float, y_relative: float) -> None:
    """Display a message when a click is received."""
    target = get_click_target(x_relative, y_relative)
    logger.info("%s clicked on %s (%s, %s)", username, target, x_relative, y_relative)


def main() -> None:
    """Run the game global event loop."""
    async_tasks: list[Task[Any]] = []

    # we didn't find a way to have this in `catch_clicks` and make the web server stop when a RuntimeError is raised
    twitch_app_token = asyncio.run(get_twitch_app_token())

    async def on_web_startup(app: web.Application) -> None:  # pylint: disable=unused-argument
        async_tasks.append(ensure_future(heat_catch_clicks(twitch_app_token, on_click)))
        async_tasks.append(ensure_future(foofurbot_catch_clicks(twitch_app_token, on_click)))

    async def on_web_shutdown(app: web.Application) -> None:  # pylint: disable=unused-argument
        for task in async_tasks:
            with suppress(Exception):
                task.cancel()

    app = web.Application()
    app.on_startup.append(on_web_startup)
    app.on_shutdown.append(on_web_shutdown)
    add_routes(app.router)
    web.run_app(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
