from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class UntappdSearchResult(_Base):
    name: str
    untpd_id: int
    url: str


class UntappdBeer(_Base):
    untpd_id: int | None = None
    untpd_url: str | None = None
    name: str | None = None
    rating: float | None = None
    checkins: int | None = None
    description: str | None = None
    style: str | None = None
    abv: float | None = None
    ibu: int | None = None
    label_hd_url: str | None = None
    label_sm_url: str | None = None
    brewery_name: str | None = None
    brewery_url: str | None = None


class UntappdBrewery(_Base):
    name: str | None = None
    description: str | None = None
    label_url: str | None = None


class UntappdCheckin(_Base):
    beer_id: int | None = None
    rating: float | None = None


class UntappdListInfo(_Base):
    list_id: int
    name: str
    item_count: int
