import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from extension.models import ExtensionConfig, ExtensionReport

REPORT = {"version": "0.5.0", "page": "search", "anchors": ["sortSelect", "cardList"]}


@pytest.mark.django_db
def test_config_missing_returns_404() -> None:
    assert APIClient().get("/extension/config/").status_code == 404


@pytest.mark.django_db
def test_config_returns_latest_data() -> None:
    ExtensionConfig.objects.create(data={"schema": 1, "anchors": {}})
    ExtensionConfig.objects.create(data={"schema": 2, "anchors": {}})

    response = APIClient().get("/extension/config/")

    assert response.json() == {"schema": 2, "anchors": {}}
    assert "public" in response["Cache-Control"]


@pytest.mark.parametrize(
    "data", [{"anchors": {}}, {"schema": "1"}, [], {"schema": 1.5}]
)
def test_config_requires_integer_schema(data: object) -> None:
    with pytest.raises(ValidationError):
        ExtensionConfig(data=data).clean()


@pytest.mark.django_db
def test_report_aggregates_counts() -> None:
    client = APIClient()

    client.post("/extension/reports/", REPORT, format="json")
    response = client.post(
        "/extension/reports/", {**REPORT, "anchors": ["sortSelect"]}, format="json"
    )

    assert response.status_code == 204
    counts = dict(ExtensionReport.objects.values_list("anchor", "count"))
    assert counts == {"sortSelect": 2, "cardList": 1}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {**REPORT, "version": "latest"},
        {**REPORT, "page": "admin"},
        {**REPORT, "anchors": []},
        {**REPORT, "anchors": ["<script>"]},
        {**REPORT, "anchors": [f"a{i}" for i in range(21)]},
    ],
)
def test_report_rejects_invalid_payload(payload: dict) -> None:
    response = APIClient().post("/extension/reports/", payload, format="json")

    assert response.status_code == 400
    assert not ExtensionReport.objects.exists()
