from __future__ import annotations

from io import StringIO

from beers.models import Beer
from django.core.management import call_command


def _call_command_with_output(command: str, *args, **kwargs) -> str:
    out = StringIO()
    kwargs["stdout"] = out
    call_command(command, *args, **kwargs)
    return out.getvalue()


def update_beers_from_vmp() -> str:
    return _call_command_with_output("update_beers_from_vmp")


def match_untpd() -> str:
    return _call_command_with_output("match_untpd_brute")


def match_untpd_scrape(**kwargs) -> str:
    calls = kwargs.get("calls", 50)
    return _call_command_with_output("match_untpd_scrape", calls)


def update_beers_from_untpd() -> str:
    return _call_command_with_output("update_beers_from_untpd")


def update_beers_from_untpd_scrape(**kwargs) -> str:
    calls = kwargs.get("calls", 50)
    return _call_command_with_output("update_beers_from_untpd_scrape", calls)


def update_details_from_vmp(calls: int) -> str:
    return _call_command_with_output("update_details_from_vmp", calls)


def update_stock_from_vmp(stores: int) -> str:
    return _call_command_with_output("update_stock_from_vmp", stores)


def update_stores_from_vmp() -> str:
    return _call_command_with_output("update_stores_from_vmp")


def smart_update_untappd_scrape(**kwargs) -> str:
    calls = kwargs.get("calls", 50)

    beers_without_untpd = Beer.objects.filter(
        untpd_id__isnull=True, match_manually=False, active=True
    ).exists()

    command = (
        "match_untpd_scrape"
        if beers_without_untpd
        else "update_beers_from_untpd_scrape"
    )
    return _call_command_with_output(command, calls)


def get_users_friendlist(user: str | None = None, full: bool = False) -> str:
    args = (user,) if user is not None else ()
    return _call_command_with_output("get_users_friendlist", *args, full=full)


def deactivate_inactive(days: int) -> str:
    return _call_command_with_output("deactivate_inactive", days)


def get_unreleased_beers_from_vmp() -> str:
    return _call_command_with_output("get_unreleased_beers_from_vmp")


def remove_match_manually() -> str:
    return _call_command_with_output("remove_match_manually")


def create_badges_untpd() -> str:
    return _call_command_with_output("create_badges_untpd")


def create_badges_custom(products: list[int], badge_text: str, badge_type: str) -> str:
    return _call_command_with_output(
        "create_badges_custom",
        products=products,
        badge_text=badge_text,
        badge_type=badge_type,
    )


def remove_badges(badge_type: str) -> str:
    return _call_command_with_output("remove_badges", badge_type)


def add_release(
    name: str, products: list[int], badge_text: str, badge_type: str, days: int
) -> str:
    return _call_command_with_output(
        "add_release",
        name=name,
        products=products,
        badge_text=badge_text,
        badge_type=badge_type,
        days=days,
    )


def create_release(name: str, products: list[int]) -> str:
    return _call_command_with_output(
        "create_release",
        name=name,
        products=products,
    )
