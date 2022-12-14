# Generated by Django 4.1.3 on 2022-11-19 06:20
from typing import Any

import django.db.models.deletion
from django.apps.registry import Apps
from django.db import migrations, models
from django.db.models import F, OuterRef, Subquery


def set_game_field(apps: Apps, schema_editor: Any) -> None:
    OccupiedTile = apps.get_model("core", "OccupiedTile")
    PlayerInGame = apps.get_model("core", "PlayerInGame")

    OccupiedTile.objects.annotate(
        new_game_id=Subquery(PlayerInGame.objects.filter(id=OuterRef("player_in_game_id")).values("game_id")[:1])
    ).update(game=F("new_game_id"))


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_remove_occupied_tiles_and_actions_player_id_and_game_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="occupiedtile",
            name="game",
            field=models.ForeignKey(
                help_text="Game the tile is in.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.game",
            ),
        ),
        migrations.RunPython(set_game_field, reverse_code=migrations.RunPython.noop),
    ]
