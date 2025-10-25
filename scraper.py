import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


@dataclass
class Listing:
    url: str
    title: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    posted_at: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


class ScraperError(Exception):
    """Base exception for scraper errors."""


def fetch_html(url: str) -> BeautifulSoup:
    """Fetch a URL and return a BeautifulSoup parser instance."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network failure paths
        raise ScraperError(f"Failed to fetch '{url}': {exc}") from exc

    return BeautifulSoup(response.text, "html.parser")


def parse_listing_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Extract all unique listing URLs from the overview page."""
    links: List[str] = []
    seen = set()
    for article in soup.select("article.aditem"):  # Standard listing container
        anchor = article.select_one("a[href]")
        if not anchor:
            continue
        href = anchor.get("href")
        if not href:
            continue
        absolute_url = urljoin(base_url, href)
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        links.append(absolute_url)

    # Fallback: try other known container classes if nothing found
    if not links:
        for anchor in soup.select("a[href*='/s-anzeige/']"):
            href = anchor.get("href")
            if not href:
                continue
            absolute_url = urljoin(base_url, href)
            if absolute_url in seen:
                continue
            seen.add(absolute_url)
            links.append(absolute_url)

    return links


def parse_detail_page(url: str) -> Listing:
    """Fetch and parse a listing detail page."""
    soup = fetch_html(url)

    def extract_text(selector: str) -> Optional[str]:
        element = soup.select_one(selector)
        if element:
            return " ".join(element.get_text(strip=True).split())
        return None

    attributes: Dict[str, str] = {}
    for row in soup.select("ul.addetailslist li"):
        key_elem = row.select_one("span.addetailslist--key")
        value_elem = row.select_one("span.addetailslist--value")
        key = key_elem.get_text(strip=True) if key_elem else None
        value = value_elem.get_text(" ", strip=True) if value_elem else None
        if key and value:
            attributes[key] = value

    return Listing(
        url=url,
        title=extract_text("h1#viewad-title"),
        price=extract_text("h2#viewad-price"),
        description=extract_text("#viewad-description-text"),
        location=extract_text("#viewad-locality"),
        posted_at=extract_text("#viewad-extra-info span"),
        attributes=attributes,
    )


def prompt_for_url() -> str:
    try:
        return input("Ebay Kleinanzeigen URL'sini giriniz: ").strip()
    except EOFError:
        raise ScraperError("No URL provided.")


def save_to_json(listings: List[Listing], output_path: Path) -> None:
    payload = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "count": len(listings),
        "listings": [asdict(listing) for listing in listings],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    url = prompt_for_url()
    if not url:
        print("Geçerli bir URL giriniz.")
        return 1

    print("Sayfa indiriliyor...")
    try:
        soup = fetch_html(url)
    except ScraperError as error:
        print(error)
        return 1

    listing_links = parse_listing_links(soup, url)
    if not listing_links:
        print("Hiç listing bulunamadı. Lütfen URL'yi kontrol ediniz.")
        return 1

    print(f"{len(listing_links)} adet ilan bulundu. Detaylar çekiliyor...")
    listings: List[Listing] = []
    for idx, link in enumerate(listing_links, start=1):
        print(f"[{idx}/{len(listing_links)}] {link}")
        try:
            listing = parse_detail_page(link)
        except ScraperError as error:
            print(f"  Hata: {error}")
            continue
        listings.append(listing)
        time.sleep(1)  # Küçük gecikme ile siteye nazikçe davran

    if not listings:
        print("Hiçbir ilan başarıyla alınamadı.")
        return 1

    output_filename = f"ebay_listings_{int(time.time())}.json"
    output_path = Path.cwd() / output_filename
    save_to_json(listings, output_path)
    print(f"Toplam {len(listings)} ilan kaydedildi: {output_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScraperError as exc:
        print(exc)
        raise SystemExit(1)
