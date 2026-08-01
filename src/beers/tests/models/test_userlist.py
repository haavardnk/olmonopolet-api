import datetime

import pytest

from beers.models import UntappdList, UserList
from beers.tests.factories import UserFactory


@pytest.mark.django_db
class TestUserListType:
    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({}, "standard"),
            ({"show_store": True}, "shopping"),
            ({"show_vintage": True}, "cellar"),
            ({"event_date": datetime.date(2030, 1, 1)}, "event"),
            ({"show_store": True, "show_vintage": True}, "shopping"),
        ],
    )
    def test_computed_on_save(self, kwargs: dict, expected: str) -> None:
        user_list = UserList.objects.create(user=UserFactory(), name="List", **kwargs)

        assert user_list.list_type == expected

    def test_untappd_list_wins(self) -> None:
        untappd_list = UntappdList.objects.create(
            untappd_list_id=1, untappd_username="user", name="Wishlist"
        )
        user_list = UserList.objects.create(
            user=UserFactory(), name="List", show_store=True, untappd_list=untappd_list
        )

        assert user_list.list_type == "untappd"
        assert user_list.is_untappd is True
