"""Create a videos from all turns of a game."""
from pathlib import Path
from typing import Optional, cast

import ffmpeg  # type: ignore[import]
import numpy as np
from tqdm import tqdm

from hexpo_game import django_setup  # noqa: F401  # pylint: disable=unused-import
from hexpo_game.core.constants import ActionState
from hexpo_game.core.grid import ConcreteGrid, Grid
from hexpo_game.core.models import Action, Game, PlayerInGame
from hexpo_game.core.types import Color, Point, Tile

# pylint: disable=too-many-locals


def make_video(
    game: Game,
    path: Path | str,
    turn_by_frame: int = 1,
    fps: int = 60,
    width: int = 1920,
    height: int = 1080,
    max_turns: Optional[int] = None,
    seconds_last_frame: int = 5,
) -> None:
    """Create a video from all turns of a game, with a turn per frame.

    Only works, for now, for game where all actions are `ActionType.GROW` and `ActionState.SUCCESS`.
    """
    tile_size = ConcreteGrid.compute_tile_size(game.grid_nb_cols, game.grid_nb_rows, width, height)
    grid = ConcreteGrid(Grid(game.grid_nb_cols, game.grid_nb_rows), tile_size)

    tiles_per_owner: dict[PlayerInGame, list[Tile]]
    tiles_owners: dict[Tile, PlayerInGame] = {}

    video_map = np.zeros((height, width, 3), dtype=np.uint8)
    offset = Point((width - grid.map.shape[1]) // 2, (height - grid.map.shape[0]) // 2)
    used_video_map = video_map[
        int(offset.y) : int(offset.y + grid.map.shape[0]), int(offset.x) : int(offset.x + grid.map.shape[1])
    ]

    writing_process = (
        ffmpeg.input("pipe:", format="rawvideo", pix_fmt="rgb24", s=f"{width}x{height}", r=fps)
        .output(str(path), pix_fmt="yuv420p", vcodec="libx264", r=fps)
        .overwrite_output()
        .run_async(pipe_stdin=True)
    )

    frame: bytes = grid.map.tobytes()
    pigs = {pig.id: pig for pig in PlayerInGame.objects.filter(game_id=game.id)}
    actions = Action.objects.filter(game_id=game.id, state=ActionState.SUCCESS).order_by("confirmed_at")
    last_turn = -1
    nb_actions = actions.count()
    last_index = nb_actions - 1
    for index, action in tqdm(enumerate(actions), desc="Action", total=nb_actions):
        tiles_owners[Tile(cast(int, action.tile_col), cast(int, action.tile_row))] = pigs[action.player_in_game_id]

        if index == last_index or (action.turn > last_turn and not action.turn % turn_by_frame):
            tiles_per_owner = {}
            for tile, owner in tiles_owners.items():
                tiles_per_owner.setdefault(owner, []).append(tile)
            grid.reset_map()
            for owner, tiles in tiles_per_owner.items():
                grid.draw_areas(tiles, Color.from_hex(owner.color), use_transparency=False)
            used_video_map[:] = grid.map[:, :, :3]
            frame = video_map.tobytes()
            writing_process.stdin.write(frame)
            last_turn = action.turn
            if max_turns is not None and last_turn >= max_turns:
                break

    for _ in range(seconds_last_frame * fps):
        writing_process.stdin.write(frame)
