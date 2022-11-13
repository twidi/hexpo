"""Main entry point for the game."""

from asyncio import Task, ensure_future
from contextlib import suppress
from typing import Any

from aiohttp import web

from hexpo_game.core.twitch_click import catch_clicks

from .core.views import add_routes


def main() -> None:
    """Run the game global event loop."""
    async_tasks: list[Task[Any]] = []

    async def on_web_startup(app: web.Application) -> None:  # pylint: disable=unused-argument
        async_tasks.append(ensure_future(catch_clicks()))

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
