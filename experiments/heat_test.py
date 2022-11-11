"""
This experiment test how to get who and where a user clicked on the stream, using the heat extension.
Inspired by https://github.com/scottgarner/Heat/blob/master/js/heat.js
"""
import asyncio
import json
import re
import sys
from datetime import datetime

import aiohttp
import websockets

CHANNEL_ID = 229962991
WS_URL = f"wss://heat-api.j38.net/channel/{CHANNEL_ID}"
GET_USER_URL = "https://heat-api.j38.net/user/{}"
valid_number_re = re.compile(r"^((1(\.0)?)|(0(\.\d+)?))$")

refused_ids = set()


async def main():
    async with aiohttp.ClientSession() as http:
        while True:
            async with websockets.connect(WS_URL) as ws:
                while True:
                    try:
                        raw_message = await ws.recv()
                    except Exception as exc:
                        print(f"[{datetime.now()}] Failed to receive WS message: {exc}", file=sys.stderr)
                        break
                    # print("Received message:", raw_message)
                    try:
                        message = json.loads(raw_message)
                    except json.JSONDecodeError:
                        print(f"[{datetime.now()}] Invalid JSON: {raw_message}", file=sys.stderr)
                        continue

                    try:
                        message_type = message["type"]
                        user_id = message["id"]
                        x_relative_str = message["x"]
                        y_relative_str = message["y"]
                    except KeyError:
                        print(f"[{datetime.now()}] Invalid message: {message}", file=sys.stderr)
                        continue
                    if message_type != "click":
                        print(f"[{datetime.now()}] Invalid message type: {message_type}", file=sys.stderr)
                        continue
                    if not user_id:
                        print(f"[{datetime.now()}] Invalid user ID: {user_id}", file=sys.stderr)
                        continue
                    if not valid_number_re.match(x_relative_str):
                        print(f"[{datetime.now()}] Invalid x: {x_relative_str}", file=sys.stderr)
                        continue
                    if not valid_number_re.match(y_relative_str):
                        print(f"[{datetime.now()}] Invalid y: {y_relative_str}", file=sys.stderr)
                        continue
                    x_relative = float(x_relative_str)
                    y_relative = float(y_relative_str)
                    if not 0 <= x_relative <= 1:
                        print(f"[{datetime.now()}] Invalid x: {x_relative}", file=sys.stderr)
                        continue
                    if not 0 <= y_relative <= 1:
                        print(f"[{datetime.now()}] Invalid y: {y_relative}", file=sys.stderr)
                        continue
                    if user_id.startswith("A"):
                        if user_id not in refused_ids:
                            print(f"[{datetime.now()}] User is anonymous: {user_id}", file=sys.stderr)
                            refused_ids.add(user_id)
                        continue
                    if user_id.startswith("U"):
                        if user_id not in refused_ids:
                            print(f"[{datetime.now()}] User did not share its id: {user_id}", file=sys.stderr)
                            refused_ids.add(user_id)
                        continue

                    try:
                        get_url = GET_USER_URL.format(user_id)
                        async with http.get(get_url) as response:
                            user = await response.json()
                    except aiohttp.ClientError:
                        print(f"[{datetime.now()}] Failed to get user: {user_id}", file=sys.stderr)
                        continue

                    try:
                        display_name = user["display_name"]
                    except KeyError:
                        print(f"[{datetime.now()}] Invalid user: {user}", file=sys.stderr)
                        continue

                    print(f"[{datetime.now()}] User {display_name} clicked at ({x_relative}, {y_relative})")


if __name__ == "__main__":
    asyncio.run(main())
