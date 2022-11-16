"""Main entry point for the game."""
import asyncio
from asyncio import Task, ensure_future
from contextlib import suppress
from typing import Any

import django
from aiohttp import web

django.setup()  # isort: skip

from .core.twitch_click import (  # noqa: E402  # pylint: disable=wrong-import-position
    catch_clicks,
    get_twitch_app_token,
)
from .core.views import (  # noqa: E402  # pylint: disable=wrong-import-position
    add_routes,
)


def main() -> None:
    """Run the game global event loop."""
    async_tasks: list[Task[Any]] = []

    # we didn't find a way to have this in `catch_clicks` and make the web server stop when a RuntimeError is raised
    twitch_app_token = asyncio.run(get_twitch_app_token())

    async def on_web_startup(app: web.Application) -> None:  # pylint: disable=unused-argument
        async_tasks.append(ensure_future(catch_clicks(twitch_app_token)))

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
