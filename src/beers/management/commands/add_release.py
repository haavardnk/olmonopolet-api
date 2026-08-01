from __future__ import annotations

from argparse import ArgumentParser
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule

from beers.models import VmpNotReleased


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--name", type=str, required=True)
        parser.add_argument("--products", type=str, required=True)
        parser.add_argument("--badge_text", type=str, required=True)
        parser.add_argument("--badge_type", type=str, required=True)
        parser.add_argument("--days", type=int, required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        name = options["name"]
        products = options["products"]
        badge_text = options["badge_text"]
        badge_type = options["badge_type"]
        days = options["days"]

        created_count = self._create_unreleased_products(products)
        self._schedule_tasks(
            name, products, badge_text, badge_type, days, created_count
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created_count} unreleased products and scheduled tasks"
            )
        )

    def _create_unreleased_products(self, products: str) -> int:
        created = VmpNotReleased.objects.bulk_create(
            [
                VmpNotReleased(id=int(product_id.strip()))
                for product_id in products.split(",")
            ]
        )
        return len(created)

    def _schedule_tasks(
        self,
        name: str,
        products: str,
        badge_text: str,
        badge_type: str,
        days: int,
        created_count: int,
    ) -> None:
        now = timezone.now()
        tasks = [
            (
                "Get beers from vmp",
                "beers.tasks.get_unreleased_beers_from_vmp",
                None,
                now,
            ),
            (
                "Add release model",
                "beers.tasks.create_release",
                f"products='{products}', name='{name}'",
                now + timedelta(minutes=10),
            ),
            (
                "Add badges",
                "beers.tasks.create_badges_custom",
                f"products='{products}', badge_text='{badge_text}', badge_type='{badge_type}'",
                now + timedelta(minutes=10),
            ),
            (
                "Remove badges",
                "beers.tasks.remove_badges",
                f"badge_type='{badge_type}'",
                now + timedelta(days=days),
            ),
            (
                "Update Untappd",
                "beers.tasks.update_beers_from_untappd",
                f"calls={created_count}",
                now + timedelta(minutes=5),
            ),
        ]

        for label, func, kwargs, next_run in tasks:
            Schedule.objects.create(
                name=f"Release: {badge_text} - {label}",
                func=func,
                kwargs=kwargs,
                schedule_type=Schedule.ONCE,
                next_run=next_run,
            )
