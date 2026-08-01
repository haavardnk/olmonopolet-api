from clients.untappd import parsers

BEER_JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{"sku": "12345", "name": "Lervig Hazy IPA",
 "description": "Juicy",
 "aggregateRating": {"ratingValue": "4.12", "reviewCount": "9876"}}
</script>
<meta property="og:url" content="https://untappd.com/b/lervig-hazy-ipa/12345" />
</head><body>
<p class="brewery"><a href="/lervig">Lervig</a></p>
<p class="style">IPA - New England</p>
<p class="abv">6.5% ABV</p>
<p class="ibu">40 IBU</p>
<a class="label image-big" data-image="https://untappd.com//hd.jpg">
  <img src="https://untappd.com/sm.jpg" />
</a>
</body></html>
"""

BEER_HTML_FALLBACK = """
<html><head>
<meta property="og:url" content="https://untappd.com/b/fallback-beer/777" />
</head><body>
<p class="brewery"><a href="https://untappd.com/brewery/aegir">Ægir</a></p>
<div class="name"><h1>Sumbel</h1></div>
<div class="caps" data-rating="3.75"></div>
<p class="raters">1234 Ratings</p>
<div class="beer-descrption-read-less">Porter</div>
</body></html>
"""

BREWERY_HTML = """
<html><head>
<script type="application/ld+json">
{"@type": "Brewery", "name": "Lervig", "description": "Stavanger",
 "image": {"contentUrl": "https://untappd.com//logo.jpg"}}
</script>
</head></html>
"""

CHECKIN_HTML = """
<html><body>
<a class="label" href="/beer/lervig-hazy-ipa/12345"></a>
<div class="caps" data-rating="4.25"></div>
</body></html>
"""

CHECKIN_FALLBACK_HTML = """
<html><body>
<p class="beer-name"><a href="/b/some-beer/999"></a></p>
<span class="rating">3.5</span>
</body></html>
"""


class TestParseBeer:
    def test_json_ld_fields(self) -> None:
        beer = parsers.parse_beer(BEER_JSON_LD_HTML)
        assert beer.untpd_id == 12345
        assert beer.name == "Lervig Hazy IPA"
        assert beer.rating == 4.12
        assert beer.checkins == 9876
        assert beer.description == "Juicy"
        assert beer.style == "IPA - New England"
        assert beer.abv == 6.5
        assert beer.ibu == 40
        assert beer.label_hd_url == "https://untappd.com/hd.jpg"
        assert beer.label_sm_url == "https://untappd.com/sm.jpg"
        assert beer.brewery_name == "Lervig"
        assert beer.brewery_url == "https://untappd.com/lervig"
        assert beer.untpd_url == "https://untappd.com/b/lervig-hazy-ipa/12345"

    def test_html_fallback_fields(self) -> None:
        beer = parsers.parse_beer(BEER_HTML_FALLBACK)
        assert beer.untpd_id == 777
        assert beer.name == "Ægir Sumbel"
        assert beer.rating == 3.75
        assert beer.checkins == 1234
        assert beer.description == "Porter"
        assert beer.brewery_url == "https://untappd.com/brewery/aegir"


class TestParseBrewery:
    def test_json_ld_fields(self) -> None:
        brewery = parsers.parse_brewery(BREWERY_HTML)
        assert brewery.name == "Lervig"
        assert brewery.description == "Stavanger"
        assert brewery.label_url == "https://untappd.com/logo.jpg"


class TestParseCheckin:
    def test_label_link_and_caps_rating(self) -> None:
        checkin = parsers.parse_checkin(CHECKIN_HTML)
        assert checkin.beer_id == 12345
        assert checkin.rating == 4.25

    def test_beer_name_link_and_span_rating(self) -> None:
        checkin = parsers.parse_checkin(CHECKIN_FALLBACK_HTML)
        assert checkin.beer_id == 999
        assert checkin.rating == 3.5


class TestParseBeerIds:
    def test_deduplicates(self) -> None:
        html = '<a href="/b/a/1"></a><a href="/b/b/2"></a><a href="/b/a/1"></a>'
        assert parsers.parse_beer_ids(html) == [1, 2]
