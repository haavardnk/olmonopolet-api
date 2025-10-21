import cloudscraper25
import xmltodict
from beers.models import Beer, ExternalAPI, VmpNotReleased
from django.core.management.base import BaseCommand
from django.utils import timezone


def call_api(url):
    scraper = cloudscraper25.create_scraper(interpreter="nodejs")
    request = scraper.get(url).text
    response = xmltodict.parse(request)

    return response


class Command(BaseCommand):
    # Updates all beers from a list of products ID's of unreleased beers.
    # For use before releases.

    def handle(self, *args, **options):
        baseurl = ExternalAPI.objects.get(name="vinmonopolet_v3").baseurl

        updated = 0
        created = 0

        products = VmpNotReleased.objects.all()

        for product in products:
            url = baseurl + "products/" + str(product.id)
            try:
                response = call_api(url)["product"]

                try:
                    beer = Beer.objects.get(vmp_id=int(response["code"]))
                    beer.vmp_name = response["name"]
                    beer.main_category = response["main_category"]["name"]
                    if "main_sub_category" in response:
                        beer.sub_category = response["main_sub_category"]["name"]
                    beer.country = response["main_country"]["name"]
                    beer.volume = float(response["volume"]["value"]) / 100.0
                    if "price" in response:
                        beer.price = response["price"]["value"]
                        beer.price_per_volume = float(response["price"]["value"]) / (
                            float(response["volume"]["value"]) / 100.0
                        )
                    beer.product_selection = response["product_selection"]
                    beer.vmp_url = "https://www.vinmonopolet.no" + response["url"]
                    beer.vmp_updated = timezone.now()
                    if not beer.active:
                        beer.active = True
                    beer.save()

                    updated += 1
                    product.delete()

                except Beer.DoesNotExist:
                    beer = Beer.objects.create(
                        vmp_id=int(response["code"]),
                        vmp_name=response["name"],
                        main_category=response["main_category"]["name"],
                        country=response["main_country"]["name"],
                        volume=float(response["volume"]["value"]) / 100.0,
                        product_selection=response["product_selection"],
                        vmp_url="https://www.vinmonopolet.no" + response["url"],
                        vmp_updated=timezone.now(),
                    )
                    if "main_sub_category" in response:
                        beer.sub_category = response["main_sub_category"]["name"]
                    if "price" in response:
                        beer.price = response["price"]["value"]
                        beer.price_per_volume = float(response["price"]["value"]) / (
                            float(response["volume"]["value"]) / 100.0
                        )
                    beer.save()

                    created += 1
                    product.delete()

            except Exception:
                continue

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} beers and created {created} new beers!"
            )
        )
