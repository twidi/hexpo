"""Test websocket stuff."""

import asyncio
import logging
from asyncio import Task

import pytest
from websockets.legacy.client import connect
from websockets.legacy.server import WebSocketServer, WebSocketServerProtocol, serve

logger = logging.getLogger(__name__)

TEST_WS = ("127.0.0.1", 8766)


async def on_server_received_message(websocket: WebSocketServerProtocol) -> None:
    """Handle a message received by the server."""
    async for message in websocket:
        await websocket.send(f"{message}")  # type: ignore[str-bytes-safe]
        await websocket.send(f"{message}2")  # type: ignore[str-bytes-safe]


async def start_server() -> Task[WebSocketServer]:
    """Start a websocket server."""
    server = await serve(
        on_server_received_message,
        TEST_WS[0],
        TEST_WS[1],
    )
    # can't figure the mypy error:
    #  Argument 1 to "create_task" has incompatible type "Coroutine[Any, Any, None]";
    #  expected
    # "Union[Generator[Any, None, WebSocketServer], Coroutine[Any, Any, WebSocketServer]]"
    return asyncio.create_task(server.serve_forever())  # type: ignore[arg-type]


async def stop_server(server_task: Task[WebSocketServer]) -> None:
    """Stop a websocket server."""
    server_task.cancel()
    while not server_task.cancelled():
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_breaking_if_not_receiving() -> None:
    """Test that we can stop a websocket if it does not receive anything."""

    server_task = await start_server()

    async with connect(f"ws://{TEST_WS[0]}:{TEST_WS[1]}") as websocket:
        await websocket.send("test")
        assert await websocket.recv() == "test"
        message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
        assert message == "test2"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(websocket.recv(), timeout=0.1)

    await stop_server(server_task)
