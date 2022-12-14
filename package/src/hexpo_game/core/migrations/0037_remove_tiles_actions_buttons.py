# Generated by Django 4.1.3 on 2022-12-15 03:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_game_end_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="action",
            name="action_type",
            field=models.CharField(
                choices=[
                    ("attack", "Attaquer"),
                    ("defend", "Défendre"),
                    ("grow", "Conquérir"),
                    ("bank", "Banquer"),
                    ("tile", "Case"),
                ],
                help_text="Type of the action.",
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="action",
            name="failure_reason",
            field=models.CharField(
                choices=[
                    ("dead", "Dead"),
                    ("bad-first", "Bad first"),
                    ("grow_self", "Already it's tile"),
                    ("grow_protected", "Tile is protected"),
                    ("grow_no_neighbor", "Not on a neighbor"),
                    ("attack_protected", "Tile is protected"),
                ],
                help_text="Reason of the failure.",
                max_length=255,
                null=True,
            ),
        ),
    ]
