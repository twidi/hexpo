# Generated by Django 4.1.3 on 2022-12-03 21:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_banked_actions_is_float"),
    ]

    operations = [
        migrations.AlterField(
            model_name="occupiedtile",
            name="level",
            field=models.FloatField(default=20, help_text="Current level of the tile. Max 100. Destroyed at 0."),
        ),
    ]