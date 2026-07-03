from __future__ import annotations

from typing import Any

from beers.models import Badge, Beer
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args: Any, **options: Any) -> None:
        self._clear_existing_badges()
        styles = self._get_unique_styles()
        created_count = self._create_badges_for_styles(styles)

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} badges."))

    def _clear_existing_badges(self) -> None:
        Badge.objects.filter(type="Top Style").delete()

    def _get_unique_styles(self) -> list[str]:
        all_styles = (
            Beer.objects.order_by("style")
            .values_list("style", flat=True)
            .distinct("style")
            .exclude(style__in=["Other", "Gluten-Free"])
        )

        base_styles = []
        for style in all_styles:
            if style:
                base_styles.append(style.split("-")[0])

        unique_styles = list(dict.fromkeys(base_styles))
        unique_styles.append("Gluten-Free")

        return unique_styles

    def _create_badges_for_styles(self, styles: list[str]) -> int:
        created_count = 0

        for style in styles:
            beers = Beer.objects.filter(style__startswith=style, active=True).order_by(
                "-rating"
            )

            badge_count = self._calculate_badge_count(beers.count())

            for index, beer in enumerate(beers[:badge_count]):
                Badge.objects.create(
                    beer=beer,
                    text=f"#{index + 1} {style}",
                    type="Top Style",
                )
                created_count += 1

        return created_count

    def _calculate_badge_count(self, beer_count: int) -> int:
        thresholds = [(300, 25), (100, 15), (50, 10), (25, 5), (10, 3)]
        return next(
            (badges for threshold, badges in thresholds if beer_count >= threshold), 0
        )
