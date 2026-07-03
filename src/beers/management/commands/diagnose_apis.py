from __future__ import annotations

import cloudscraper25
from beers.models import Store
from beers.vmp.commands import VmpCommand

_BLOCK_MARKERS = ("just a moment", "cf-chl", "attention required", "cloudflare")


class Command(VmpCommand):
    help = "Probe vinmonopolet and untappd from this host to detect IP blocks"

    def handle(self, *args, **options) -> None:
        client = self.get_client()

        self._probe("vmp øl (no store)", client.probe(client.search_url("øl")))

        store = Store.objects.order_by("store_stock_updated").first()
        if store is not None:
            self._probe(
                f"vmp øl (store {store.store_id})",
                client.probe(client.search_url("øl", store_id=store.store_id)),
            )

        self._probe_untappd()

    def _probe(self, label: str, result: tuple[int | None, str, int, str]) -> None:
        status, ctype, length, snippet = result
        verdict = self._verdict(status, ctype, snippet)
        self.stdout.write(
            f"{label}: status={status} ctype={ctype} len={length} -> {verdict}"
        )
        if verdict != "OK":
            self.stdout.write(self.style.WARNING(snippet[:200] or "<no body>"))

    def _probe_untappd(self) -> None:
        scraper = cloudscraper25.create_scraper(browser="chrome", enable_stealth=True)
        try:
            response = scraper.get("https://untappd.com/search?q=test", timeout=30)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"untappd: request failed ({exc})"))
            return
        snippet = response.text[:300]
        verdict = self._verdict(
            response.status_code, response.headers.get("content-type", ""), snippet
        )
        self.stdout.write(
            f"untappd search: status={response.status_code} "
            f"len={len(response.text)} -> {verdict}"
        )
        if verdict != "OK":
            self.stdout.write(self.style.WARNING(snippet[:200]))

    def _verdict(self, status: int | None, ctype: str, snippet: str) -> str:
        if status is None:
            return "NO RESPONSE (network/timeout)"
        if status in (403, 429, 503):
            return f"BLOCKED ({status})"
        if any(marker in snippet.lower() for marker in _BLOCK_MARKERS):
            return "BLOCKED (cloudflare challenge)"
        if status == 200:
            return "OK"
        return f"UNEXPECTED ({status})"
