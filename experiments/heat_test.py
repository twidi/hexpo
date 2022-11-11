"""
This experiment test how to get who and where a user clicked on the stream, using the heat extension.
Inspired by https://github.com/scottgarner/Heat/blob/master/js/heat.js
"""
import asyncio
import json
import sys

import aiohttp
import websockets

CHANNEL_ID = 229962991
WS_URL = f"wss://heat-api.j38.net/channel/{CHANNEL_ID}"
GET_USER_URL = "https://heat-api.j38.net/user/{}"


async def main():
    async with websockets.connect(WS_URL) as ws, aiohttp.ClientSession() as http:
        while True:
            raw_message = await ws.recv()
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                print("Invalid JSON:", raw_message, file=sys.stderr)
                continue

            try:
                message_type = message["type"]
                user_id = message["id"]
                x_relative = float(message["x"])
                y_relative = float(message["y"])
            except (KeyError, ValueError):
                print("Invalid message:", message, file=sys.stderr)

                continue
            if message_type != "click":
                print("Invalid message type:", message_type, file=sys.stderr)
                continue
            if not user_id:
                print("Invalid user ID:", user_id, file=sys.stderr)
                continue
            if not 0 <= x_relative < 1:
                print("Invalid x:", x_relative, file=sys.stderr)
                continue
            if not 0 <= y_relative < 1:
                print("Invalid y:", y_relative, file=sys.stderr)
                continue
            if user_id.startswith("A"):
                print("User is anonymous:", user_id, file=sys.stderr)
                continue
            if user_id.startswith("U"):
                print("User did not share its id:", user_id, file=sys.stderr)
                continue

            try:
                get_url = GET_USER_URL.format(user_id)
                async with http.get(get_url) as response:
                    user = await response.json()
            except aiohttp.ClientError:
                print("Failed to get user:", user_id, file=sys.stderr)
                continue

            try:
                display_name = user["display_name"]
            except KeyError:
                print("Invalid user:", user, file=sys.stderr)
                continue

            print(f"User {display_name} clicked at ({x_relative}, {y_relative})")


if __name__ == "__main__":
    asyncio.run(main())
