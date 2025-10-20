from datetime import timedelta

from beers.models import VmpNotReleased
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--name", type=str)
        parser.add_argument("--products", type=str)
        parser.add_argument("--badge_text", type=str)
        parser.add_argument("--badge_type", type=str)
        parser.add_argument("--days", type=int)

    def handle(self, *args, **options):
        created = 0

        # Add beers to watch
        for product in options["products"].split(","):
            VmpNotReleased.objects.create(id=int(product))
            created += 1

        # Schedule getting beer infos from vmp now
        Schedule.objects.create(
            name="Release: " + options["badge_text"] + " - Get beers from vmp",
            func="beers.tasks.get_unreleased_beers_from_vmp",
            schedule_type=Schedule.ONCE,
            next_run=timezone.now(),
        )

        # Schedule adding release model
        Schedule.objects.create(
            name="Release: " + options["badge_text"] + " - Add release model",
            func="beers.tasks.create_release",
            kwargs="products='"
            + options["products"]
            + "', name='"
            + options["name"]
            + "'",
            schedule_type=Schedule.ONCE,
            next_run=timezone.now() + timedelta(minutes=10),
        )

        # Schedule adding badges
        Schedule.objects.create(
            name="Release: " + options["badge_text"] + " - Add badges",
            func="beers.tasks.create_badges_custom",
            kwargs="products='"
            + options["products"]
            + "', badge_text='"
            + options["badge_text"]
            + "', badge_type='"
            + options["badge_type"]
            + "'",
            schedule_type=Schedule.ONCE,
            next_run=timezone.now() + timedelta(minutes=10),
        )

        # Schedule removing badges
        Schedule.objects.create(
            name="Release: " + options["badge_text"] + " - Remove badges",
            func="beers.tasks.remove_badges",
            kwargs="badge_type='" + options["badge_type"] + "'",
            schedule_type=Schedule.ONCE,
            next_run=timezone.now() + timedelta(days=options["days"]),
        )

        # Schedule untappd updates
        update_runs = 0
        if created < 50:
            update_runs = 3
        elif created < 150:
            update_runs = 5
        else:
            update_runs = 7

        for update_run in range(0, update_runs):
            Schedule.objects.create(
                name="Release: "
                + options["badge_text"]
                + " - Update Untappd "
                + str(update_run + 1),
                func="beers.tasks.smart_update_untappd",
                schedule_type=Schedule.ONCE,
                next_run=timezone.now() + timedelta(minutes=5),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created} unreleased products and scheduled tasks"
            )
        )
