from __future__ import annotations

import re

import feedparser
import requests as http_requests
from rest_framework import serializers

from beers.models import UntappdRssFeed, WrongMatch


class WrongMatchSerializer(serializers.ModelSerializer):
    beer_name = serializers.CharField(read_only=True, source="beer.vmp_name")
    current_untpd_url = serializers.CharField(read_only=True, source="beer.untpd_url")
    current_untpd_id = serializers.CharField(read_only=True, source="beer.untpd_id")

    class Meta:
        model = WrongMatch
        fields = [
            "beer",
            "beer_name",
            "current_untpd_url",
            "current_untpd_id",
            "suggested_url",
        ]


class UntappdRssFeedSerializer(serializers.ModelSerializer):
    class Meta:
        model = UntappdRssFeed
        fields = ["feed_url", "last_synced", "active", "created_at"]
        read_only_fields = ["last_synced", "created_at"]

    def validate_feed_url(self, value: str) -> str:
        if "untappd.com/rss/user/" not in value:
            raise serializers.ValidationError(
                "URL må være en Untappd RSS-feed (https://untappd.com/rss/user/...)"
            )
        match = re.search(r"untappd\.com/rss/user/([^?/]+)", value)
        if not match:
            raise serializers.ValidationError("Kunne ikke hente brukernavn fra RSS-URL")
        if "key=" not in value:
            raise serializers.ValidationError(
                "RSS-URL mangler nøkkelparameter. Bruk den fullstendige URLen fra Untappd RSS-innstillinger."
            )
        username = match.group(1)
        try:
            resp = http_requests.get(
                f"https://untappd.com/user/{username}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
                allow_redirects=True,
            )
            if (
                resp.status_code == 404
                or "set their account to be private" in resp.text
            ):
                raise serializers.ValidationError(
                    "Untappd-profilen er privat. Sett profilen til offentlig for å bruke RSS-synkronisering."
                )
        except serializers.ValidationError:
            raise
        except Exception:
            pass
        try:
            parsed = feedparser.parse(value)
            if parsed.bozo and not parsed.entries:
                raise serializers.ValidationError(
                    "RSS-feeden kunne ikke lastes. Kontroller at URLen er riktig."
                )
        except serializers.ValidationError:
            raise
        except Exception:
            pass
        return value
