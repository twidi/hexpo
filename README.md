# `Hexpocalypse Later`

## Introduction

`Hexpocalypse Later`, codename `hexpo` (hence the repository name), is a turn-based game where players start with a 
single hexagonal tile and must expand their territory by colonizing new tiles, while defending.

The game is made to be played by viewers of a Twitch stream, by clicking directly on the stream.

It is partially developed and playable (at least when we'll have a first playable version) on [Twidi's Twitch](https://www.twitch.tv/twidi_angel), and on [Twidi's Discord](https://discord.gg/EJjmVNDRUN).

Here is the mindmap from the brainstorming made with viewers on the first stream about this game (click for large version): 

[![Mindmap](resources/mindmap-2022-11-11.png)](https://raw.githubusercontent.com/twidi/hexpo/main/resources/mindmap-2022-11-11.png)

And here is the first wireframe on how it will look on stream (click for large version):

[![Wireframe](resources/wireframe-2022-11-11.png)](https://raw.githubusercontent.com/twidi/hexpo/main/resources/wireframe-2022-11-11.png)

The purple hexagon is where the webcam of the streamer is, the top left block is where players will pick their actions,
and the game will be run in the main area.

## About the name

The name `Hexpocalypse Later` was proposed by GPT-3 after a long time of brainstorming and giving up... Some people 
should have the reference (hint: an old movie) :wink:


## Stack

The game will be made in pure [python (3.10)](https://python.org), and the rendering will be a simple HTML page created with [Django](https://www.djangoproject.com/) and serverd with [aiohttp](https://github.com/aio-libs/aiohttp) (django async is not as great as it should/could be), updated via [SSE](https://wikipedia.org/wiki/Server-sent_events) (via [aiohttp-sse](https://github.com/aio-libs/aiohttp-sse)), thanks to [Htmx](https://htmx.org). We'll get the coordinates of the players clicks via [websocket](https://en.wikipedia.org/wiki/WebSocket) using the [Heat Twitch Extension](https://dashboard.twitch.tv/extensions/cr20njfkgll4okyrhag7xxph270sqk-2.1.1).
