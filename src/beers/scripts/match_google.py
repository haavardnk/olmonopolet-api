import os
import re
from collections.abc import Iterable

import requests

from beers.models import Beer

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
UNTAPPD_BEER_URL = re.compile(r"^https://untappd\.com/b/[^/]+/\d+$")
MAX_RESULTS = 5


def query_google(beer_name: str) -> list[tuple[str, str]]:
    response = requests.get(
        SEARCH_URL,
        params={
            "key": os.getenv("GOOGLE_API_KEY"),
            "cx": os.getenv("GOOGLE_CUSTOM_SEARCH_ID"),
            "q": beer_name,
        },
        timeout=30,
    )
    if response.status_code != 200:
        print(
            f"Failed to fetch results for {beer_name}. "
            f"Status code: {response.status_code}"
        )
        return []

    results = [
        (item.get("title", ""), item["link"])
        for item in response.json().get("items", [])
        if UNTAPPD_BEER_URL.match(item.get("link", ""))
    ]
    return results[:MAX_RESULTS]


def match_with_google(beers: Iterable[Beer]) -> None:
    for beer in beers:
        print(f"\nProcessing beer: {beer.vmp_name}")

        results = query_google(beer.vmp_name)
        if not results:
            print("No results found. Skipping this beer.")
            continue

        print(f"\nTop {len(results)} results:")
        for i, (title, link) in enumerate(results, start=1):
            print(f"{i}. {title} - {link}")

        choice = (
            input(
                "\nEnter the number of the correct match, add 'j' for christmas "
                "(e.g. 2j), or press Enter to skip: "
            )
            .strip()
            .lower()
        )
        is_christmas = choice.endswith("j")
        choice = choice.removesuffix("j")

        if choice.isdigit() and 1 <= int(choice) <= len(results):
            title, link = results[int(choice) - 1]
            beer.untpd_url = link
            beer.untpd_id = int(link.split("/")[-1])
            beer.verified_match = True
            beer.match_manually = False
            if is_christmas:
                beer.is_christmas_beer = True
            beer.save()

            suffix = " + marked as Christmas beer" if is_christmas else ""
            print(f"Matched '{beer.vmp_name}' to '{title}' ({link}){suffix}.")
        elif is_christmas and not choice:
            beer.is_christmas_beer = True
            beer.save()
            print(f"Marked '{beer.vmp_name}' as Christmas beer (no match).")
        else:
            print("No match selected. Skipping this beer.")

    print("\n✓ All beers processed!")


if __name__ == "__main__":
    match_with_google(Beer.objects.filter(untpd_id__isnull=True, active=True))
