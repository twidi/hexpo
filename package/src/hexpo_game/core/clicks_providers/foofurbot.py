"""Get positions of clicks from users on Twitch via the FoofurBot extension.

Extension: https://dashboard.twitch.tv/extensions/nyu70xf8pcgznu09ho55zo9x5z6ao8-0.0.1

See also a http fork: https://dashboard.twitch.tv/extensions/qillvtd91t2sywoxafyag186blg8jy-0.0.1

"""

import asyncio
import logging

from websockets.legacy.server import WebSocketServerProtocol, serve

logger = logging.getLogger("hexpo_game.click_provider.foofurbot")


async def on_message(websocket: WebSocketServerProtocol) -> None:
    """Handle message received via the websocket."""
    async for message in websocket:
        print("RECEIVED", message)


async def main() -> None:
    """Listen on the websocket forever."""
    server = await serve(on_message, "127.0.0.1", 8765)
    logger.info("Websocket listening")
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
