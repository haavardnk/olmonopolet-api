import sys
from datetime import timedelta

from django.utils import timezone

from beers.models import Beer, Release

UNTAPPD_FIELDS = (
    "untpd_id",
    "untpd_name",
    "untpd_url",
    "brewery",
    "rating",
    "checkins",
    "style",
    "description",
    "abv",
    "ibu",
    "label_hd_url",
    "label_sm_url",
    "alcohol_units",
    "untpd_updated",
)


def reject_match(beer: Beer) -> None:
    for field in UNTAPPD_FIELDS:
        setattr(beer, field, None)
    beer.verified_match = False
    beer.prioritize_recheck = False
    beer.match_manually = True
    beer.save()


def review_matches(release: Release) -> None:
    beers = release.beer.filter(
        verified_match=False,
        untpd_id__isnull=False,
        created_at__gte=timezone.now() - timedelta(days=30),
    ).exclude(untpd_name="")

    for beer in beers:
        print(f"\n{'=' * 60}")
        print(f"VMP Name: {beer.vmp_name}")
        print(f"Untappd Name: {beer.untpd_name}")
        print(f"{'=' * 60}")

        answer = (
            input("Is this a verified match? (y/n/j for christmas): ").strip().lower()
        )

        if answer == "y":
            beer.verified_match = True
            beer.save()
            print("✓ Verified match set to True.\n")
        elif answer == "j":
            beer.verified_match = True
            beer.is_christmas_beer = True
            beer.save()
            print("✓ Verified match set to True + marked as Christmas beer.\n")
        elif answer == "n":
            reject_match(beer)
            print("✗ Fields reset and saved.\n")
        else:
            print("⚠ Invalid input. Skipping this beer.\n")

    print("\n✓ All beers processed!")


def latest_release() -> Release:
    return Release.objects.filter(release_date__isnull=False).latest("release_date")


if __name__ == "__main__":
    release = (
        Release.objects.get(name=sys.argv[1]) if len(sys.argv) > 1 else latest_release()
    )
    review_matches(release)
