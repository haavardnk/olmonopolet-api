import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("beers", "0121_brewery_alter_beer_brewery"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="beer",
            name="brewery",
        ),
        migrations.DeleteModel(
            name="Brewery",
        ),
        migrations.CreateModel(
            name="Brewery",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(blank=True, max_length=200, null=True)),
                (
                    "untpd_url",
                    models.CharField(
                        max_length=250,
                        unique=True,
                        validators=[django.core.validators.URLValidator()],
                    ),
                ),
                (
                    "label_url",
                    models.CharField(
                        blank=True,
                        max_length=250,
                        null=True,
                        validators=[django.core.validators.URLValidator()],
                    ),
                ),
                ("description", models.TextField(blank=True, null=True)),
                ("untpd_updated", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name_plural": "Breweries",
            },
        ),
        migrations.AddField(
            model_name="beer",
            name="brewery",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="beers",
                to="beers.brewery",
            ),
        ),
    ]
