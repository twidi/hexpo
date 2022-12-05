"""Main entry point for the game."""
import asyncio
import logging
from asyncio import Task, ensure_future
from contextlib import suppress
from functools import partial
from typing import Any

from aiohttp import web

from hexpo_game.core.types import GameMessagesQueue

from . import django_setup  # noqa: F401  # pylint: disable=unused-import
from .core.clicks_providers.foofurbot import catch_clicks as foofurbot_catch_clicks
from .core.clicks_providers.heat import catch_clicks as heat_catch_clicks
from .core.clicks_providers.utils import init_refused_ids
from .core.game import ClicksQueue, dequeue_clicks, get_game_and_grid, on_click
from .core.twitch import ChatMessagesQueue, get_twitch_client, get_twitch_tokens
from .core.views import prepare_views

logger = logging.getLogger("hexpo_game")


def main() -> None:
    """Run the game global event loop."""
    async_tasks: list[Task[Any]] = []

    game, grid = get_game_and_grid()

    clicks_queue: ClicksQueue = asyncio.Queue()
    chat_messages_queue: ChatMessagesQueue = asyncio.Queue()
    game_messages_queue: GameMessagesQueue = asyncio.Queue()
    click_callback = partial(on_click, game=game, grid=grid, clicks_queue=clicks_queue)

    async def on_web_startup(app: web.Application) -> None:  # pylint: disable=unused-argument
        token, refresh_token = await get_twitch_tokens()
        twitch_client = get_twitch_client(token, refresh_token)
        async_tasks.append(twitch_client.running_task)
        refused_ids = await init_refused_ids()
        async_tasks.append(
            ensure_future(heat_catch_clicks(twitch_client, chat_messages_queue, refused_ids, click_callback))
        )
        async_tasks.append(
            ensure_future(foofurbot_catch_clicks(twitch_client, chat_messages_queue, refused_ids, click_callback))
        )
        async_tasks.append(
            ensure_future(dequeue_clicks(clicks_queue, game, grid.grid, chat_messages_queue, game_messages_queue))
        )
        async_tasks.append(ensure_future(twitch_client.send_messages(chat_messages_queue)))
        async_tasks.append(ensure_future(game_state.update_forever(game_messages_queue, delay=1)))

    async def on_web_shutdown(app: web.Application) -> None:  # pylint: disable=unused-argument
        await clicks_queue.join()
        await chat_messages_queue.join()
        for task in async_tasks:
            with suppress(Exception):
                task.cancel()

    app = web.Application()
    game_state = prepare_views(app.router)
    app.on_startup.append(on_web_startup)
    app.on_shutdown.append(on_web_shutdown)
    web.run_app(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
