"""Scraper for extracting detailed data from eBay vehicle listings.

This module provides an ``EbayCarScraper`` class that can iterate over a list of
listing URLs, visit each page and collect structured information about the car
and the seller. The scraper relies on CSS selectors (which can be customised via
``selector_config``) to locate pieces of information on the detail pages.

Example usage from the command line::

    python scraper.py --input urls.txt --output listings.json

Where ``urls.txt`` contains one vehicle detail URL per line. The resulting JSON
file will contain an array of records with all requested fields.

Due to the dynamic nature of the website you may need to adjust the selectors in
``DEFAULT_SELECTORS`` (or supply your own configuration file via
``--selectors``). The script is designed to fail gracefully when a selector does
not match, recording missing values as ``None``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


LOGGER = logging.getLogger(__name__)


DEFAULT_SEARCH_URL = (
    "https://www.kleinanzeigen.de/s-autos/stockach/"
    "c216l8477r100+autos.ez_i:1910%2C+autos.km_i:1%2C+autos.power_i:1%2C"
)


@dataclass
class SellerInfo:
    """Structured information about the listing's seller."""

    name: Optional[str] = None
    active_since: Optional[str] = None
    seller_type: Optional[str] = None
    phone_number: Optional[str] = None
    online_listing_count: Optional[int] = None


@dataclass
class CarListing:
    """Structured information collected from an eBay vehicle listing."""

    url: str
    listing_id: Optional[str] = None
    title: Optional[str] = None
    price: Optional[str] = None
    address: Optional[str] = None
    date: Optional[str] = None
    view_count: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    mileage_km: Optional[str] = None
    damage_status: Optional[str] = None
    first_registration_date: Optional[str] = None
    fuel_type: Optional[str] = None
    horsepower: Optional[str] = None
    transmission: Optional[str] = None
    description: Optional[str] = None
    seller: SellerInfo = field(default_factory=SellerInfo)
    extra_attributes: Dict[str, Any] = field(default_factory=dict)


DEFAULT_SELECTORS: Dict[str, str] = {
    "listing_id": '[data-testid="ux-layout-section-module"] [data-testid="item-id"]',
    "title": 'h1[itemprop="name"], h1[data-testid="vehicle-title"]',
    "price": '[data-testid="vehicle-price"] span, span[itemprop="price"]',
    "address": '[data-testid="seller-address"], [data-testid="location-section"]',
    "date": '[data-testid="seller-info-section"] time, time[itemprop="datePosted"]',
    "view_count": '[data-testid="pageview-count"], span:contains("views")',
    "brand": '[data-testid="make-value"], [data-qa="vehicle-make"]',
    "model": '[data-testid="model-value"], [data-qa="vehicle-model"]',
    "mileage_km": '[data-testid="mileage-value"], [data-qa="vehicle-mileage"]',
    "damage_status": '[data-testid="damageCondition-value"], [data-qa="vehicle-damaged"]',
    "first_registration_date": '[data-testid="firstRegistration-value"], [data-qa="vehicle-first-registration"]',
    "fuel_type": '[data-testid="fuelType-value"], [data-qa="vehicle-fuel"]',
    "horsepower": '[data-testid="horsepower-value"], [data-qa="vehicle-power"]',
    "transmission": '[data-testid="transmission-value"], [data-qa="vehicle-transmission"]',
    "description": '[data-testid="description-read-more"] section, [data-testid="vehicle-description"]',
    "seller_name": '[data-testid="seller-name"]',
    "seller_active_since": '[data-testid="seller-active-since"], [data-qa="seller-since"]',
    "seller_type": '[data-testid="seller-type"], [data-qa="seller-type"]',
    "seller_phone": '[data-testid="call-seller-button"]',
    "seller_online_listing_count": '[data-testid="seller-other-items-count"], [data-qa="seller-offer-count"]',
    "attribute_rows": '[data-testid="attribute-list"] li, [data-testid="specification-list"] li',
}


ATTRIBUTE_FIELD_MAP: Dict[str, str] = {
    "marke": "brand",
    "make": "brand",
    "fahrzeugmarke": "brand",
    "modell": "model",
    "model": "model",
    "fahrzeugmodell": "model",
    "kilometerstand": "mileage_km",
    "mileage": "mileage_km",
    "laufleistung": "mileage_km",
    "mileage from odometer": "mileage_km",
    "zustand": "damage_status",
    "damage condition": "damage_status",
    "unfallfahrzeug": "damage_status",
    "schaden": "damage_status",
    "fahrzeugzustand": "damage_status",
    "erstzulassung": "first_registration_date",
    "first registration": "first_registration_date",
    "registration date": "first_registration_date",
    "kraftstoffart": "fuel_type",
    "fuel type": "fuel_type",
    "kraftstoff": "fuel_type",
    "leistung": "horsepower",
    "power": "horsepower",
    "motorleistung": "horsepower",
    "ps": "horsepower",
    "getriebe": "transmission",
    "transmission": "transmission",
    "beschreibung": "description",
    "description": "description",
    "fahrzeugbeschreibung": "description",
    "aufrufe": "view_count",
    "besucher": "view_count",
    "page views": "view_count",
    "besichtigungen": "view_count",
    "ort": "address",
    "standort": "address",
    "adresse": "address",
}


class EbayCarScraper:
    """Scrape eBay vehicle listings for car and seller metadata."""

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        selector_config: Optional[Dict[str, str]] = None,
        timeout: int = 15,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.selectors = DEFAULT_SELECTORS.copy()
        if selector_config:
            self.selectors.update(selector_config)

    def _normalize_value(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            normalized = re.sub(r"\s+", " ", value).strip()
            return normalized or None
        return str(value)

    def _apply_if_missing(self, listing: CarListing, field: str, value: Any) -> None:
        if getattr(listing, field):
            return
        normalized = self._normalize_value(value)
        if normalized:
            setattr(listing, field, normalized)

    def _apply_seller_field(self, seller: SellerInfo, field: str, value: Any) -> None:
        current = getattr(seller, field)
        if current:
            return
        if field == "online_listing_count":
            if value is None:
                return
            if isinstance(value, (int, float)):
                seller.online_listing_count = int(value)
                return
            if isinstance(value, str):
                digits = re.findall(r"\d+", value.replace(".", ""))
                if digits:
                    seller.online_listing_count = int(digits[0])
                return
            return
        normalized = self._normalize_value(value)
        if normalized:
            setattr(seller, field, normalized)

    def extract_json_ld(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                LOGGER.debug("Failed to decode JSON-LD block", exc_info=True)
                continue
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        entries.append(item)
            elif isinstance(data, dict):
                entries.append(data)
        return entries

    def extract_vehicle_json_ld(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        for entry in self.extract_json_ld(soup):
            entry_type = entry.get("@type")
            if isinstance(entry_type, list):
                if any(t.lower() in {"car", "vehicle"} for t in entry_type if isinstance(t, str)):
                    return entry
            elif isinstance(entry_type, str) and entry_type.lower() in {"car", "vehicle", "product"}:
                return entry
        return None

    def extract_next_data(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        script = soup.find("script", attrs={"id": "__NEXT_DATA__", "type": "application/json"})
        if not script or not script.string:
            return None
        try:
            return json.loads(script.string)
        except json.JSONDecodeError:
            LOGGER.debug("Failed to decode __NEXT_DATA__ payload", exc_info=True)
            return None

    @staticmethod
    def deep_get(data: Any, path: Iterable[Any]) -> Any:
        current = data
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and isinstance(key, int):
                if key < len(current):
                    current = current[key]
                else:
                    return None
            else:
                return None
            if current is None:
                return None
        return current

    def extract_item_from_next_data(self, next_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidate_paths = [
            ("props", "pageProps", "listingModel", "item"),
            ("props", "pageProps", "viewItemResponse", "item"),
            ("props", "pageProps", "pageData", "item"),
        ]
        for path in candidate_paths:
            item = self.deep_get(next_data, path)
            if isinstance(item, dict):
                return item
        return None

    def format_price_info(self, price_info: Any) -> Optional[str]:
        if isinstance(price_info, dict):
            value = (
                price_info.get("value")
                or price_info.get("convertedValue")
                or price_info.get("price")
                or price_info.get("amount")
            )
            currency = (
                price_info.get("currency")
                or price_info.get("currencyId")
                or price_info.get("priceCurrency")
            )
            if value is None and isinstance(price_info.get("amount"), (int, float)):
                value = price_info.get("amount")
            if value is None:
                return None
            if currency:
                return f"{value} {currency}"
            return str(value)
        return self._normalize_value(price_info)

    def extract_structured_attributes_from_item(self, item: Dict[str, Any]) -> Dict[str, str]:
        attributes: Dict[str, str] = {}

        specifics = self.deep_get(item, ("itemSpecifics", "nameValueList"))
        if isinstance(specifics, list):
            for entry in specifics:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                value = entry.get("value") or entry.get("values")
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value if v)
                if name and value:
                    attributes[name] = str(value)

        attribute_groups = item.get("attributeGroups")
        if isinstance(attribute_groups, list):
            for group in attribute_groups:
                if not isinstance(group, dict):
                    continue
                for attribute in group.get("attributes", []):
                    if not isinstance(attribute, dict):
                        continue
                    name = attribute.get("name") or attribute.get("displayName")
                    value = attribute.get("value") or attribute.get("displayValue")
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value if v)
                    if name and value:
                        attributes[name] = str(value)

        additional = item.get("additionalProductInformation")
        if isinstance(additional, list):
            for entry in additional:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name") or entry.get("label")
                value = entry.get("value")
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value if v)
                if name and value:
                    attributes[name] = str(value)

        return attributes

    def populate_from_attributes(self, listing: CarListing, attributes: Dict[str, str]) -> None:
        for key, raw_value in attributes.items():
            if not key:
                continue
            normalized_key = key.strip().lower()
            field = ATTRIBUTE_FIELD_MAP.get(normalized_key)
            if not field:
                continue
            self._apply_if_missing(listing, field, raw_value)

    def enrich_from_structured_data(self, listing: CarListing, soup: BeautifulSoup) -> Dict[str, str]:
        collected_attributes: Dict[str, str] = {}

        vehicle_entry = self.extract_vehicle_json_ld(soup)
        if vehicle_entry:
            self._apply_if_missing(listing, "title", vehicle_entry.get("name"))
            offers = vehicle_entry.get("offers")
            if isinstance(offers, dict):
                self._apply_if_missing(listing, "price", self.format_price_info(offers))
            brand = vehicle_entry.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            self._apply_if_missing(listing, "brand", brand)
            model = vehicle_entry.get("model")
            if isinstance(model, dict):
                model = model.get("name")
            self._apply_if_missing(listing, "model", model)
            mileage = vehicle_entry.get("mileageFromOdometer")
            if isinstance(mileage, dict):
                value = mileage.get("value")
                unit = mileage.get("unitCode") or mileage.get("unitText")
                if value is not None:
                    mileage_value = f"{value} {unit}" if unit else str(value)
                    self._apply_if_missing(listing, "mileage_km", mileage_value)
            self._apply_if_missing(listing, "fuel_type", vehicle_entry.get("fuelType"))
            transmission = vehicle_entry.get("vehicleTransmission")
            if isinstance(transmission, dict):
                transmission = transmission.get("name")
            self._apply_if_missing(listing, "transmission", transmission)
            engine = vehicle_entry.get("vehicleEngine")
            if isinstance(engine, dict):
                power = engine.get("power") or engine.get("horsepower") or engine.get("enginePower")
                if isinstance(power, dict):
                    value = power.get("value")
                    unit = power.get("unitCode") or power.get("unitText")
                    if value is not None:
                        power = f"{value} {unit}" if unit else str(value)
                self._apply_if_missing(listing, "horsepower", power)
            self._apply_if_missing(listing, "description", vehicle_entry.get("description"))
            self._apply_if_missing(listing, "date", vehicle_entry.get("datePosted") or vehicle_entry.get("datePublished"))
            self._apply_if_missing(listing, "listing_id", vehicle_entry.get("sku") or vehicle_entry.get("productID"))
            address = vehicle_entry.get("address")
            if isinstance(address, dict):
                parts = [
                    address.get("streetAddress"),
                    address.get("addressLocality"),
                    address.get("postalCode"),
                    address.get("addressCountry"),
                ]
                address = ", ".join(part for part in parts if part)
            self._apply_if_missing(listing, "address", address)
            additional = vehicle_entry.get("additionalProperty")
            if isinstance(additional, list):
                for prop in additional:
                    if not isinstance(prop, dict):
                        continue
                    name = prop.get("name")
                    value = prop.get("value")
                    if name and value:
                        collected_attributes[name] = str(value)
            seller_data = vehicle_entry.get("seller")
            if isinstance(seller_data, dict):
                self._apply_seller_field(listing.seller, "name", seller_data.get("name"))
                self._apply_seller_field(listing.seller, "seller_type", seller_data.get("@type"))

        next_data = self.extract_next_data(soup)
        if next_data:
            item = self.extract_item_from_next_data(next_data)
            if item:
                self._apply_if_missing(listing, "listing_id", item.get("legacyItemId") or item.get("itemId"))
                self._apply_if_missing(listing, "title", item.get("title"))
                self._apply_if_missing(listing, "description", self.deep_get(item, ("itemDescription", "text")) or item.get("description"))
                price_info = item.get("price") or self.deep_get(item, ("pricingSummary", "price"))
                formatted_price = self.format_price_info(price_info)
                if formatted_price:
                    self._apply_if_missing(listing, "price", formatted_price)
                location = item.get("itemLocation")
                address_value: Optional[str] = None
                if isinstance(location, dict):
                    parts = [
                        location.get("addressLine1") or location.get("address1"),
                        location.get("city") or location.get("cityName"),
                        location.get("stateOrProvince"),
                        location.get("postalCode"),
                        location.get("country"),
                    ]
                    address_value = ", ".join(part for part in parts if part)
                elif isinstance(location, str):
                    address_value = location
                self._apply_if_missing(listing, "address", address_value)
                self._apply_if_missing(listing, "date", item.get("itemCreationDate") or item.get("creationDate"))
                metrics = item.get("itemMetrics")
                if isinstance(metrics, dict):
                    self._apply_if_missing(listing, "view_count", metrics.get("pageViewCount") or metrics.get("watchCount"))

                seller_block = item.get("seller") or item.get("sellerInfo")
                if isinstance(seller_block, dict):
                    self._apply_seller_field(listing.seller, "name", seller_block.get("username") or seller_block.get("companyName") or seller_block.get("name"))
                    self._apply_seller_field(listing.seller, "active_since", seller_block.get("memberSince") or seller_block.get("registrationDate"))
                    self._apply_seller_field(listing.seller, "seller_type", seller_block.get("sellerType") or seller_block.get("accountType") or seller_block.get("sellerAccountType"))
                    phone = seller_block.get("phoneNumber") or seller_block.get("sellerPhone")
                else:
                    phone = None
                self._apply_seller_field(listing.seller, "phone_number", phone or item.get("sellerContactPhoneNumber"))
                listing_count = None
                if isinstance(seller_block, dict):
                    listing_count = seller_block.get("totalActiveListings") or seller_block.get("totalListings")
                self._apply_seller_field(listing.seller, "online_listing_count", listing_count)

                structured_attributes = self.extract_structured_attributes_from_item(item)
                for key, value in structured_attributes.items():
                    if key not in collected_attributes:
                        collected_attributes[key] = value

        return collected_attributes

    def fetch_soup(self, url: str) -> BeautifulSoup:
        LOGGER.debug("Fetching %s", url)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def extract_listing_urls_from_search(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        selectors = [
            "article[data-testid='result-list-entry'] a[href*='/s-anzeige/']",
            "li.ad-listitem a[href*='/s-anzeige/']",
            "a[data-testid='result-title']",
            "a[href*='/s-anzeige/']",
        ]
        seen: Dict[str, None] = {}
        for selector in selectors:
            for anchor in soup.select(selector):
                href = anchor.get("href")
                if not href:
                    continue
                normalized = href.split("?")[0]
                if normalized.startswith("//"):
                    normalized = "https:" + normalized
                elif normalized.startswith("/"):
                    normalized = urljoin(base_url, normalized)
                elif not normalized.startswith("http"):
                    normalized = urljoin(base_url, normalized)
                if "/s-anzeige/" not in normalized:
                    continue
                seen.setdefault(normalized, None)
        return list(seen.keys())

    def collect_listing_urls(self, search_url: str) -> List[str]:
        soup = self.fetch_soup(search_url)
        listing_urls = self.extract_listing_urls_from_search(soup, search_url)
        LOGGER.info("Found %d listing URLs on %s", len(listing_urls), search_url)
        return listing_urls

    def parse_text(self, soup: BeautifulSoup, selector: Optional[str]) -> Optional[str]:
        if not selector:
            return None
        for single_selector in selector.split(","):
            element = soup.select_one(single_selector.strip())
            if element:
                if element.has_attr("content"):
                    return element["content"].strip()
                if element.name == "a" and element.has_attr("href") and not element.text.strip():
                    return element["href"].strip()
                text = element.get_text(" ", strip=True)
                if text:
                    return text
        return None

    def parse_listing_id(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        listing_id = self.parse_text(soup, self.selectors.get("listing_id"))
        if listing_id:
            return listing_id
        match = re.search(r"/(\d{7,})", url)
        if match:
            return match.group(1)
        meta = soup.find("meta", {"name": "keywords"})
        if meta and meta.get("content"):
            alt_match = re.search(r"(\d{7,})", meta["content"])
            if alt_match:
                return alt_match.group(1)
        return None

    def parse_seller(self, soup: BeautifulSoup) -> SellerInfo:
        online_listing_count_text = self.parse_text(
            soup, self.selectors.get("seller_online_listing_count")
        )
        online_listing_count: Optional[int] = None
        if online_listing_count_text:
            digits = re.findall(r"\d+", online_listing_count_text.replace(".", ""))
            if digits:
                online_listing_count = int(digits[0])
        return SellerInfo(
            name=self.parse_text(soup, self.selectors.get("seller_name")),
            active_since=self.parse_text(soup, self.selectors.get("seller_active_since")),
            seller_type=self.parse_text(soup, self.selectors.get("seller_type")),
            phone_number=self.parse_text(soup, self.selectors.get("seller_phone")),
            online_listing_count=online_listing_count,
        )

    def parse_attribute_rows(self, soup: BeautifulSoup) -> Dict[str, str]:
        attributes: Dict[str, str] = {}
        selector = self.selectors.get("attribute_rows")
        if not selector:
            return attributes
        for row in soup.select(selector):
            key_element = row.select_one("span, dt")
            value_element = row.select_one("strong, dd") or row.find("span", class_=False)
            key = key_element.get_text(" ", strip=True) if key_element else None
            value = value_element.get_text(" ", strip=True) if value_element else None
            if key and value:
                attributes[key] = value
        return attributes

    def parse_listing_details(self, url: str) -> CarListing:
        soup = self.fetch_soup(url)
        seller = self.parse_seller(soup)
        attribute_rows = self.parse_attribute_rows(soup)
        listing = CarListing(
            url=url,
            listing_id=self.parse_listing_id(soup, url),
            title=self.parse_text(soup, self.selectors.get("title")),
            price=self.parse_text(soup, self.selectors.get("price")),
            address=self.parse_text(soup, self.selectors.get("address")),
            date=self.parse_text(soup, self.selectors.get("date")),
            view_count=self.parse_text(soup, self.selectors.get("view_count")),
            brand=self.parse_text(soup, self.selectors.get("brand")),
            model=self.parse_text(soup, self.selectors.get("model")),
            mileage_km=self.parse_text(soup, self.selectors.get("mileage_km")),
            damage_status=self.parse_text(soup, self.selectors.get("damage_status")),
            first_registration_date=self.parse_text(
                soup, self.selectors.get("first_registration_date")
            ),
            fuel_type=self.parse_text(soup, self.selectors.get("fuel_type")),
            horsepower=self.parse_text(soup, self.selectors.get("horsepower")),
            transmission=self.parse_text(soup, self.selectors.get("transmission")),
            description=self.parse_text(soup, self.selectors.get("description")),
            seller=seller,
            extra_attributes=attribute_rows,
        )
        if attribute_rows:
            self.populate_from_attributes(listing, attribute_rows)
        structured_attributes = self.enrich_from_structured_data(listing, soup)
        for key, value in structured_attributes.items():
            listing.extra_attributes.setdefault(key, value)
        if structured_attributes:
            self.populate_from_attributes(listing, structured_attributes)
        return listing

    def scrape(self, urls: Iterable[str]) -> List[CarListing]:
        listings: List[CarListing] = []
        for url in urls:
            url = url.strip()
            if not url:
                continue
            try:
                listings.append(self.parse_listing_details(url))
            except requests.HTTPError as exc:
                LOGGER.error("Failed to fetch %s: %s", url, exc)
            except Exception:  # pragma: no cover - guard for unexpected parsing errors
                LOGGER.exception("Unexpected error while parsing %s", url)
        return listings


def save_output(path: Path, listings: List[CarListing]) -> None:
    data = [asdict(listing) for listing in listings]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_selector_config(path: Optional[Path]) -> Optional[Dict[str, str]]:
    if not path:
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape detailed eBay vehicle listings")
    parser.add_argument(
        "--search-url",
        default=DEFAULT_SEARCH_URL,
        help=(
            "Kleinanzeigen search results URL whose listings should be scraped. "
            "Defaults to the Stockach automotive search provided by the client."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output.json"),
        help="Path where the JSON output should be written. Defaults to 'output.json'.",
    )
    parser.add_argument(
        "--selectors",
        type=Path,
        default=None,
        help=(
            "Optional JSON file with CSS selectors to override the defaults. "
            "The file must contain a mapping from field name to selector string."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Verbosity of log output.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Timeout (in seconds) for HTTP requests.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(message)s")

    search_url = args.search_url
    selector_config = load_selector_config(args.selectors)

    scraper = EbayCarScraper(selector_config=selector_config, timeout=args.timeout)
    urls = scraper.collect_listing_urls(search_url)
    if not urls:
        LOGGER.error("No listings found on %s", search_url)
        return 1
    listings = scraper.scrape(urls)
    save_output(args.output, listings)

    LOGGER.info("Saved %d listings to %s", len(listings), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
