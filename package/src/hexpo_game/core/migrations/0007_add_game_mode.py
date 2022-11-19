# Generated by Django 4.1.3 on 2022-11-18 23:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_remove_occupied_tile_nb_updates"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="mode",
            field=models.CharField(
                choices=[
                    ("free-full", "Free full"),
                    ("free-neighbor", "Free neighbor"),
                    ("turn-by-turn", "Turn by turn"),
                ],
                default="free-full",
                max_length=255,
            ),
        ),
    ]
