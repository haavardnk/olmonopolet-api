from io import StringIO

from beers.models import Beer
from django.core.management import call_command


def update_beers_from_vmp() -> str:
    out = StringIO()
    call_command("update_beers_from_vmp", stdout=out)
    return out.getvalue()


def match_untpd() -> str:
    out = StringIO()
    call_command("match_untpd_brute", stdout=out)
    return out.getvalue()


def match_untpd_scrape(**kwargs) -> str:
    calls = kwargs.get("calls", 50)
    out = StringIO()
    call_command("match_untpd_scrape", calls, stdout=out)
    return out.getvalue()


def update_beers_from_untpd() -> str:
    out = StringIO()
    call_command("update_beers_from_untpd", stdout=out)
    return out.getvalue()


def update_beers_from_untpd_scrape(**kwargs) -> str:
    calls = kwargs.get("calls", 50)
    out = StringIO()
    call_command("update_beers_from_untpd_scrape", calls, stdout=out)
    return out.getvalue()


def update_details_from_vmp(calls: int) -> str:
    out = StringIO()
    call_command("update_details_from_vmp", calls, stdout=out)
    return out.getvalue()


def update_stock_from_vmp(stores: int) -> str:
    out = StringIO()
    call_command("update_stock_from_vmp", stores, stdout=out)
    return out.getvalue()


def update_stores_from_vmp() -> str:
    out = StringIO()
    call_command("update_stores_from_vmp", stdout=out)
    return out.getvalue()


def smart_update_untappd_scrape(**kwargs) -> str:
    calls = kwargs.get("calls", 50)

    beers = Beer.objects.filter(
        untpd_id__isnull=True, match_manually=False, active=True
    )
    out = StringIO()

    if beers:
        call_command("match_untpd_scrape", calls, stdout=out)
    else:
        call_command("update_beers_from_untpd_scrape", calls, stdout=out)

    return out.getvalue()


def get_users_friendlist(user=None, full=False) -> str:
    out = StringIO()

    if user is not None:
        call_command("get_users_friendlist", user, full=full, stdout=out)
    else:
        call_command("get_users_friendlist", full=full, stdout=out)

    return out.getvalue()


def deactivate_inactive(days: int) -> str:
    out = StringIO()
    call_command("deactivate_inactive", days, stdout=out)
    return out.getvalue()


def get_unreleased_beers_from_vmp() -> str:
    out = StringIO()
    call_command("get_unreleased_beers_from_vmp", stdout=out)
    return out.getvalue()


def remove_match_manually() -> str:
    out = StringIO()
    call_command("remove_match_manually", stdout=out)
    return out.getvalue()


def create_badges_untpd() -> str:
    out = StringIO()
    call_command("create_badges_untpd", stdout=out)
    return out.getvalue()


def create_badges_custom(products: list[int], badge_text: str, badge_type: str) -> str:
    out = StringIO()
    call_command(
        "create_badges_custom",
        products=products,
        badge_text=badge_text,
        badge_type=badge_type,
        stdout=out,
    )
    return out.getvalue()


def remove_badges(badge_type: str) -> str:
    out = StringIO()
    call_command(
        "remove_badges",
        badge_type,
        stdout=out,
    )
    return out.getvalue()


def add_release(
    name: str, products: list[int], badge_text: str, badge_type: str, days: int
) -> str:
    out = StringIO()
    call_command(
        "add_release",
        name=name,
        products=products,
        badge_text=badge_text,
        badge_type=badge_type,
        days=days,
        stdout=out,
    )
    return out.getvalue()


def create_release(name: str, products: list[int]) -> str:
    out = StringIO()
    call_command(
        "create_release",
        name=name,
        products=products,
        stdout=out,
    )
    return out.getvalue()
