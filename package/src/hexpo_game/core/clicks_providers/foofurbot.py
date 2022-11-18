"""Get positions of clicks from users on Twitch via the FoofurBot extension.

Extension: https://dashboard.twitch.tv/extensions/nyu70xf8pcgznu09ho55zo9x5z6ao8-0.0.1

See also a http fork: https://dashboard.twitch.tv/extensions/qillvtd91t2sywoxafyag186blg8jy-0.0.1

"""

import asyncio
import json
import logging
from contextlib import suppress
from functools import partial

from twitchio import Client  # type: ignore[import]
from websockets.exceptions import ConnectionClosedError
from websockets.legacy.server import WebSocketServerProtocol, serve

from hexpo_game.core.clicks_providers.utils import (
    ClickCallback,
    get_twitch_client,
    handle_click,
    init_refused_ids,
    standalone_runner,
)

logger = logging.getLogger("hexpo_game.click_provider.foofurbot")


def get_data(raw_data: bytes | str) -> tuple[str, str, float, float]:
    """Get the data from a raw WS message.

    Parameters
    ----------
    raw_data: bytes | str
        The raw WS message.

    Returns
    -------
    tuple[str, float, float]
        The user ID, the event type, the x coordinate and the y coordinate.

    Raises
    ------
    ValueError
        If the data is invalid. The error will have 3 args (in ``exc_object.args``):
        - The error message (with ``%s`` placeholder for the specific data that caused the error (see below))
        - The specific data that caused the error to be raised.
        - The user id found inn the message if any (for example to store it to ignore its next messages)
    """
    # pylint warns us that we have an unused `%s` in the error message, but it's to let the called handled the message +
    # value like it wants (using `%` or not, for example with logging)
    # pylint: disable=raising-format-tuple

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON: %s", raw_data) from exc

    user_id = None
    try:
        event = data["event"]
        user_id = data["data"]["user"].get("id", data["data"]["user"]["opaqueId"])
        # that's a lot of data :D
        x_relative = data["data"]["data"]["percentX"]
        y_relative = data["data"]["data"]["percentY"]
    except KeyError as exc:
        raise ValueError("Invalid data: %s", data, user_id) from exc

    if event not in ("click", "mouseup", "mousedown"):
        raise ValueError("Invalid event: %s", event, user_id)
    if not user_id:
        raise ValueError("Invalid user ID: %s", user_id, user_id)
    if not 0 <= x_relative <= 1:
        raise ValueError("Invalid x: %s", x_relative, user_id)
    if not 0 <= y_relative <= 1:
        raise ValueError("Invalid y: %s", y_relative, user_id)

    return user_id, event, x_relative, y_relative


async def on_connection(
    websocket: WebSocketServerProtocol,
    twitch_client: Client,
    refused_ids: set[str],
    callback: ClickCallback,
) -> None:
    """Handle message received via the websocket."""
    # connection is closed relatively quickly, so we don't need to log this
    with suppress(ConnectionClosedError):
        async for raw_data in websocket:
            try:

                try:
                    user_id, event, x_relative, y_relative = get_data(raw_data)
                except ValueError as exc:
                    logger.error(str(exc.args[0]), exc.args[1])
                    if len(exc.args) > 2:
                        refused_ids.add(exc.args[2])
                    continue

                if event != "click":
                    continue

                await handle_click(user_id, x_relative, y_relative, twitch_client, refused_ids, callback)

            except Exception:  # pylint: disable=broad-except
                logger.exception("Unhandled exception while trying to process WS message: %s", raw_data)


async def catch_clicks(twitch_app_token: str, callback: ClickCallback) -> None:
    """Listen on the websocket forever."""
    twitch_client = await get_twitch_client(twitch_app_token)
    refused_ids: set[str] = await init_refused_ids()

    server = await serve(
        partial(on_connection, twitch_client=twitch_client, refused_ids=refused_ids, callback=callback),
        "127.0.0.1",
        8765,
    )
    print("Websocket listening")
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(standalone_runner(catch_clicks))
