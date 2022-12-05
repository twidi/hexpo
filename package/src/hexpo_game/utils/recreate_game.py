"""Recreate a game from another based solely on its actions."""
from datetime import datetime
from typing import Optional, cast

from tqdm import tqdm

from hexpo_game import django_setup  # noqa: F401  # pylint: disable=unused-import
from hexpo_game.core.constants import ActionState, ActionType
from hexpo_game.core.models import Action, Game, OccupiedTile, PlayerInGame
from hexpo_game.core.types import Tile

# pylint: disable=too-many-locals


def recreate_game(game: Game) -> Game:
    """Recreate a game from another based solely on its actions.

    Only works for game where all actions are `ActionType.GROW`. Non-successful actions are ignored.

    """
    game_data = vars(game).copy()
    for key in ("id", "_state", "current_turn", "ended_at"):
        del game_data[key]
    new_game = Game.objects.create(**game_data)

    current_pig_by_player_id: dict[int, PlayerInGame] = {}
    last_owner: dict[Tile, int] = {}  # value is player id
    last_tile_info = {}
    count = {}

    next_turn_min_at: Optional[datetime] = None

    old_pigs_by_id: dict[int, tuple[int, str]] = {  # player_in_game_id => (player_id, color)
        pig_id: (player_id, color)
        for pig_id, player_id, color in PlayerInGame.objects.filter(game_id=game.id).values_list(
            "id", "player_id", "color"
        )
    }
    actions = (
        Action.objects.filter(game=game, state=ActionState.SUCCESS)
        .order_by("confirmed_at")
        .values_list("player_in_game_id", "tile_col", "tile_row", "confirmed_at")
    )
    for action in tqdm(actions, desc="Action", total=actions.count()):

        now = cast(datetime, action[3])
        if next_turn_min_at is None:
            next_turn_min_at = now + game.config.step_collecting_actions_duration
            new_game.started_at = new_game.current_turn_started_at = now
        elif now > next_turn_min_at:
            new_game.current_turn += 1
            new_game.current_turn_started_at = now
            next_turn_min_at = new_game.current_turn_started_at + game.config.step_collecting_actions_duration

        tile = Tile(cast(int, action[1]), cast(int, action[2]))

        player_id = old_pigs_by_id[action[0]][0]
        if player_id not in current_pig_by_player_id:
            current_pig_by_player_id[player_id] = PlayerInGame.objects.create(
                player_id=player_id,
                game=new_game,
                started_at=now,
                started_turn=new_game.current_turn,
                color=old_pigs_by_id[action[0]][1],
                start_tile_row=tile.row,
                start_tile_col=tile.col,
            )
            # because of auto_now_add
            PlayerInGame.objects.filter(id=current_pig_by_player_id[player_id].id).update(started_at=now)
        Action.objects.create(
            player_in_game=current_pig_by_player_id[player_id],
            turn=new_game.current_turn,
            action_type=ActionType.GROW,
            tile_col=tile.col,
            tile_row=tile.row,
            confirmed_at=now,
            state=ActionState.SUCCESS,
        )
        other_player_id = last_owner.get(tile)
        if other_player_id == player_id:  # tile already owned
            continue
        last_owner[tile] = player_id
        if player_id not in count:
            count[player_id] = 0
        count[player_id] += 1
        last_tile_info[tile] = {"updated_at": now, "player_in_game": current_pig_by_player_id[player_id]}
        if other_player_id is None:
            continue
        count[other_player_id] -= 1
        if not count[other_player_id]:
            current_pig_by_player_id[other_player_id].dead_at = now
            current_pig_by_player_id[other_player_id].killed_by_id = current_pig_by_player_id[player_id].id
            current_pig_by_player_id[other_player_id].ended_turn = new_game.current_turn
            current_pig_by_player_id[other_player_id].save()
            del current_pig_by_player_id[other_player_id]

    new_game.save()  # save the turn

    for tile, tile_info in tqdm(last_tile_info.items(), desc="Tile"):
        new_tile = OccupiedTile.objects.create(game=new_game, col=tile.col, row=tile.row, **tile_info)
        # because it's an auto_now=True field
        OccupiedTile.objects.filter(pk=new_tile.pk).update(updated_at=tile_info["updated_at"])

    return new_game
