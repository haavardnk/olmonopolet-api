from django.db import migrations, models


def populate_flags(apps, schema_editor):
    UserList = apps.get_model("beers", "UserList")
    UserList.objects.filter(list_type="shopping").update(
        show_quantity=True, show_store=True
    )
    UserList.objects.filter(list_type="cellar").update(
        show_quantity=True, show_vintage=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("beers", "0115_store_stock_updated_remove_auto_now"),
    ]

    operations = [
        migrations.AddField(
            model_name="userlist",
            name="show_quantity",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="userlist",
            name="show_store",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="userlist",
            name="show_vintage",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="userlist",
            name="show_prices",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(populate_flags, migrations.RunPython.noop),
    ]
