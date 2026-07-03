from __future__ import annotations

from argparse import ArgumentParser
from datetime import timedelta
from typing import Any

from beers.models import VmpNotReleased
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule


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
        created_count = 0
        for product_id in products.split(","):
            VmpNotReleased.objects.create(id=int(product_id.strip()))
            created_count += 1
        return created_count

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

        self._schedule_get_beers_task(badge_text, now)
        self._schedule_release_model_task(name, products, badge_text, now)
        self._schedule_badges_tasks(products, badge_text, badge_type, days, now)
        self._schedule_untappd_updates(badge_text, created_count, now)

    def _schedule_get_beers_task(self, badge_text: str, now) -> None:
        Schedule.objects.create(
            name=f"Release: {badge_text} - Get beers from vmp",
            func="beers.tasks.get_unreleased_beers_from_vmp",
            schedule_type=Schedule.ONCE,
            next_run=now,
        )

    def _schedule_release_model_task(
        self, name: str, products: str, badge_text: str, now
    ) -> None:
        Schedule.objects.create(
            name=f"Release: {badge_text} - Add release model",
            func="beers.tasks.create_release",
            kwargs=f"products='{products}', name='{name}'",
            schedule_type=Schedule.ONCE,
            next_run=now + timedelta(minutes=10),
        )

    def _schedule_badges_tasks(
        self, products: str, badge_text: str, badge_type: str, days: int, now
    ) -> None:
        Schedule.objects.create(
            name=f"Release: {badge_text} - Add badges",
            func="beers.tasks.create_badges_custom",
            kwargs=f"products='{products}', badge_text='{badge_text}', badge_type='{badge_type}'",
            schedule_type=Schedule.ONCE,
            next_run=now + timedelta(minutes=10),
        )

        Schedule.objects.create(
            name=f"Release: {badge_text} - Remove badges",
            func="beers.tasks.remove_badges",
            kwargs=f"badge_type='{badge_type}'",
            schedule_type=Schedule.ONCE,
            next_run=now + timedelta(days=days),
        )

    def _schedule_untappd_updates(
        self, badge_text: str, created_count: int, now
    ) -> None:
        Schedule.objects.create(
            name=f"Release: {badge_text} - Update Untappd",
            func="beers.tasks.update_beers_from_untappd",
            kwargs=f"calls={created_count}",
            schedule_type=Schedule.ONCE,
            next_run=now + timedelta(minutes=5),
        )
