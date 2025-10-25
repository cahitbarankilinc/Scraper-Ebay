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

import requests
from bs4 import BeautifulSoup


LOGGER = logging.getLogger(__name__)


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

    def fetch_soup(self, url: str) -> BeautifulSoup:
        LOGGER.debug("Fetching %s", url)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

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
            extra_attributes=self.parse_attribute_rows(soup),
        )
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


def load_urls(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


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
        "--input",
        type=Path,
        required=True,
        help="Text file containing one listing URL per line.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path where the JSON output should be written.",
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

    urls = load_urls(args.input)
    selector_config = load_selector_config(args.selectors)

    scraper = EbayCarScraper(selector_config=selector_config, timeout=args.timeout)
    listings = scraper.scrape(urls)
    save_output(args.output, listings)

    LOGGER.info("Saved %d listings to %s", len(listings), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
