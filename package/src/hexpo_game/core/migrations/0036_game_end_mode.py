# Generated by Django 4.1.3 on 2022-12-13 23:37

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0035_add_erosion_step"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="end_mode",
            field=models.CharField(
                choices=[
                    ("endless", "Sans fin"),
                    ("turn-limit", "Nombre de tours limité"),
                    ("full-map", "100% occupation"),
                ],
                default="endless",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="game",
            name="end_mode_turn",
            field=models.PositiveIntegerField(help_text="The turn at which the game will end.", null=True),
        ),
        migrations.AddField(
            model_name="game",
            name="winner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="won_games",
                to="core.playeringame",
            ),
        ),
    ]