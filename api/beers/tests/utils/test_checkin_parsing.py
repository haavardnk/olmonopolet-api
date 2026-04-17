import io
import json
from datetime import datetime, timezone

import pytest
from beers.api.utils import (
    _extract_checkin_data,
    _parse_checkin_time,
    bulk_import_tasted,
    parse_untappd_file,
)
from beers.models import Tasted, UntappdCheckin
from beers.tests.factories import BeerFactory, UserFactory


class TestParseCheckinTime:
    def test_int_timestamp(self) -> None:
        result = _parse_checkin_time(1700000000)
        assert result == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_float_timestamp(self) -> None:
        result = _parse_checkin_time(1700000000.5)
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_datetime_string_no_tz(self) -> None:
        result = _parse_checkin_time("2024-01-15 10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_datetime_string_with_tz(self) -> None:
        result = _parse_checkin_time("Mon, 15 Jan 2024 10:30:00 +0000")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_none_returns_none(self) -> None:
        assert _parse_checkin_time(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_checkin_time("") is None

    def test_invalid_string_returns_none(self) -> None:
        assert _parse_checkin_time("not-a-date") is None


class TestExtractCheckinData:
    def test_with_bid(self) -> None:
        row = {"checkin_id": "100", "bid": "500", "rating_score": "4.5"}
        result = _extract_checkin_data(row)
        assert result is not None
        assert result[0] == 100
        assert result[1] == 500
        assert result[2] == 4.5

    def test_with_beer_id_fallback(self) -> None:
        row = {"checkin_id": "100", "beer_id": "600"}
        result = _extract_checkin_data(row)
        assert result is not None
        assert result[1] == 600

    def test_with_beer_url_fallback(self) -> None:
        row = {"checkin_id": "100", "beer_url": "https://untappd.com/beer/700"}
        result = _extract_checkin_data(row)
        assert result is not None
        assert result[1] == 700

    def test_beer_url_trailing_slash(self) -> None:
        row = {"checkin_id": "100", "beer_url": "https://untappd.com/beer/700/"}
        result = _extract_checkin_data(row)
        assert result is not None
        assert result[1] == 700

    def test_missing_checkin_id_returns_none(self) -> None:
        row = {"bid": "500"}
        assert _extract_checkin_data(row) is None

    def test_non_numeric_beer_id_returns_none(self) -> None:
        row = {"checkin_id": "100", "bid": "abc"}
        assert _extract_checkin_data(row) is None

    def test_zero_rating_returns_none(self) -> None:
        row = {"checkin_id": "100", "bid": "500", "rating_score": "0"}
        result = _extract_checkin_data(row)
        assert result is not None
        assert result[2] is None

    def test_missing_rating_returns_none(self) -> None:
        row = {"checkin_id": "100", "bid": "500"}
        result = _extract_checkin_data(row)
        assert result is not None
        assert result[2] is None

    def test_no_beer_id_at_all_returns_none(self) -> None:
        row = {"checkin_id": "100"}
        assert _extract_checkin_data(row) is None


class TestParseUntappdFile:
    def test_csv_file(self) -> None:
        content = "checkin_id,bid,rating_score\n100,500,4.5\n101,501,3.0\n"
        f = io.BytesIO(content.encode("utf-8"))
        f.name = "export.csv"
        result = parse_untappd_file(f)
        assert result is not None
        assert len(result) == 2
        assert result[0][0] == 100
        assert result[0][1] == 500

    def test_json_file(self) -> None:
        data = [
            {"checkin_id": "200", "bid": "600", "rating_score": "4.0"},
            {"checkin_id": "201", "bid": "601"},
        ]
        f = io.BytesIO(json.dumps(data).encode("utf-8"))
        f.name = "export.json"
        result = parse_untappd_file(f)
        assert result is not None
        assert len(result) == 2

    def test_json_non_list_returns_empty(self) -> None:
        f = io.BytesIO(json.dumps({"key": "val"}).encode("utf-8"))
        f.name = "export.json"
        result = parse_untappd_file(f)
        assert result == []

    def test_unsupported_extension_returns_none(self) -> None:
        f = io.BytesIO(b"data")
        f.name = "export.xlsx"
        assert parse_untappd_file(f) is None


@pytest.mark.django_db
class TestBulkImportTasted:
    def test_imports_matched_checkins(self) -> None:
        user = UserFactory()
        beer = BeerFactory(untpd_id=500)
        checkins = [
            (1001, 500, 4.5, datetime(2024, 1, 1, tzinfo=timezone.utc)),
        ]

        result = bulk_import_tasted(user, checkins)

        assert result["imported_count"] == 1
        assert result["total_check_ins"] == 1
        assert Tasted.objects.filter(user=user, beer=beer).exists()
        assert UntappdCheckin.objects.get(untpd_checkin_id=1001).synced is True

    def test_duplicate_checkins_skipped(self) -> None:
        user = UserFactory()
        BeerFactory(untpd_id=500)
        checkins = [
            (1001, 500, 4.5, datetime(2024, 1, 1, tzinfo=timezone.utc)),
        ]
        bulk_import_tasted(user, checkins)
        result = bulk_import_tasted(user, checkins)

        assert result["imported_count"] == 0
        assert Tasted.objects.filter(user=user).count() == 1

    def test_unmatched_beer_saved_not_synced(self) -> None:
        user = UserFactory()
        checkins = [
            (2001, 99999, 3.0, None),
        ]

        result = bulk_import_tasted(user, checkins)

        assert result["imported_count"] == 0
        assert UntappdCheckin.objects.filter(untpd_checkin_id=2001).exists()
        assert UntappdCheckin.objects.get(untpd_checkin_id=2001).synced is False
