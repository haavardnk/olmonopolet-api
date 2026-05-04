from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("beers", "0114_untappdlist_sync_task_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="store",
            name="store_stock_updated",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
