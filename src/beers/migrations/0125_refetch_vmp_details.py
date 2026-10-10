from django.db import migrations


def refetch_details(apps, schema_editor):
    Beer = apps.get_model("beers", "Beer")
    Beer.objects.filter(active=True).update(vmp_details_fetched=None)


class Migration(migrations.Migration):

    dependencies = [
        ('beers', '0124_vmp_facet_fields'),
    ]

    operations = [
        migrations.RunPython(refetch_details, migrations.RunPython.noop),
    ]
