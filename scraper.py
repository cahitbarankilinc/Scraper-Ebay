import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


@dataclass
class PreisInfo:
    wert: Optional[float] = None
    waehrung: Optional[str] = None
    verhandlungsbasis: bool = False


@dataclass
class Fahrzeug:
    marke: Optional[str] = None
    modell: Optional[str] = None
    preis: PreisInfo = field(default_factory=PreisInfo)
    link: Optional[str] = None
    scrapedat: Optional[str] = None
    kilometerstand: Optional[int] = None
    erstzulassung: Optional[str] = None
    leistung: Optional[str] = None
    kraftstoffart: Optional[str] = None
    getriebe: Optional[str] = None
    fahrzeugtyp: Optional[str] = None
    anzahl_tueren: Optional[str] = None
    aussenfarbe: Optional[str] = None
    material_innenausstattung: Optional[str] = None
    hu_bis: Optional[str] = None
    umweltplakette: Optional[str] = None
    schadstoffklasse: Optional[str] = None
    fahrzeugzustand: Optional[str] = None
    ausstattung: List[str] = field(default_factory=list)
    Beschreibung: Optional[str] = None
    images: List[str] = field(default_factory=list)


@dataclass
class Anzeige:
    plattform: str = "Kleinanzeigen"
    kategorie: Optional[str] = None
    anzeige_id: Optional[str] = None
    aufrufe: Optional[int] = None
    bilder: Optional[int] = None


@dataclass
class Verkaeufer:
    name: Optional[str] = None
    nutzertyp: Optional[str] = None
    aktiv_seit: Optional[str] = None
    userid: Optional[str] = None
    bewertungen: List[str] = field(default_factory=list)
    Stadt: Optional[str] = None
    ort: Optional[str] = None


@dataclass
class Listing:
    fahrzeug: Fahrzeug = field(default_factory=Fahrzeug)
    anzeige: Anzeige = field(default_factory=Anzeige)
    verkaeufer: Verkaeufer = field(default_factory=Verkaeufer)


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


def extract_text(soup: BeautifulSoup, selector: str) -> Optional[str]:
    """Extract text from an element using CSS selector."""
    element = soup.select_one(selector)
    if element:
        return " ".join(element.get_text(strip=True).split())
    return None


def extract_price_info(price_str: Optional[str]) -> PreisInfo:
    """Parse price string and extract value, currency, and negotiability."""
    preis = PreisInfo()
    if not price_str:
        return preis
    
    # Check for VB (Verhandlungsbasis)
    if "VB" in price_str or "Verhandlungsbasis" in price_str:
        preis.verhandlungsbasis = True
    
    # Extract currency
    if "€" in price_str or "EUR" in price_str:
        preis.waehrung = "EUR"
    elif "$" in price_str or "USD" in price_str:
        preis.waehrung = "USD"
    
    # Extract numeric value
    price_match = re.search(r'[\d.,]+', price_str.replace(".", "").replace(",", "."))
    if price_match:
        try:
            preis.wert = float(price_match.group().replace(",", ""))
        except ValueError:
            pass
    
    return preis


def extract_images(soup: BeautifulSoup) -> List[str]:
    """Extract all image URLs from the listing page."""
    images = []
    
    # Try different image selectors
    img_selectors = [
        'img[src*="img.kleinanzeigen.de"]',
        '#viewad-image-gallery img',
        '.galleryimage img',
        '.imagegallery img',
        'img.galleryimage-large'
    ]
    
    for selector in img_selectors:
        for img in soup.select(selector):
            src = img.get('src') or img.get('data-src')
            if src and 'kleinanzeigen.de' in src:
                # Get high resolution version
                if '$_' not in src:
                    src = src + '?rule=$_57.AUTO'
                if src not in images:
                    images.append(src)
    
    return images


def extract_equipment(soup: BeautifulSoup) -> List[str]:
    """Extract equipment/features list from the listing."""
    equipment = []
    
    # Look for equipment lists
    equipment_selectors = [
        '.attributelist--condensed li',
        'ul[class*="equipment"] li',
        'ul[class*="features"] li',
        'ul[class*="ausstattung"] li'
    ]
    
    for selector in equipment_selectors:
        for elem in soup.select(selector):
            text = elem.get_text(strip=True)
            if text and text not in equipment and len(text) > 2:
                equipment.append(text)
    
    return equipment


def extract_attributes(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract all attributes from detail list."""
    attributes = {}
    
    # Main attribute list
    for row in soup.select("ul.addetailslist li"):
        key_elem = row.select_one("span.addetailslist--key")
        value_elem = row.select_one("span.addetailslist--value")
        key = key_elem.get_text(strip=True) if key_elem else None
        value = value_elem.get_text(" ", strip=True) if value_elem else None
        if key and value:
            attributes[key] = value
    
    return attributes


def parse_detail_page(url: str) -> Listing:
    """Fetch and parse a listing detail page."""
    soup = fetch_html(url)
    
    listing = Listing()
    
    # Fahrzeug Information
    listing.fahrzeug.link = url
    listing.fahrzeug.scrapedat = datetime.utcnow().isoformat() + "Z"
    
    # Extract title and split into brand/model if possible
    title = extract_text(soup, "h1#viewad-title")
    if title:
        # Try to extract brand and model from title
        parts = title.split(maxsplit=1)
        if len(parts) >= 2:
            listing.fahrzeug.marke = parts[0]
            listing.fahrzeug.modell = parts[1]
        else:
            listing.fahrzeug.modell = title
    
    # Extract price
    price_str = extract_text(soup, "h2#viewad-price")
    listing.fahrzeug.preis = extract_price_info(price_str)
    
    # Extract description
    listing.fahrzeug.Beschreibung = extract_text(soup, "#viewad-description-text")
    
    # Extract images
    listing.fahrzeug.images = extract_images(soup)
    
    # Extract attributes
    attributes = extract_attributes(soup)
    
    # Map attributes to fields
    for key, value in attributes.items():
        key_lower = key.lower()
        
        if "marke" in key_lower or "hersteller" in key_lower:
            listing.fahrzeug.marke = value
        elif "modell" in key_lower:
            listing.fahrzeug.modell = value
        elif "kilometerstand" in key_lower or "laufleistung" in key_lower:
            km_match = re.search(r'[\d.]+', value.replace(".", ""))
            if km_match:
                try:
                    listing.fahrzeug.kilometerstand = int(km_match.group())
                except ValueError:
                    pass
        elif "erstzulassung" in key_lower or "ez" in key_lower:
            listing.fahrzeug.erstzulassung = value
        elif "leistung" in key_lower or "ps" in key_lower or "kw" in key_lower:
            listing.fahrzeug.leistung = value
        elif "kraftstoff" in key_lower or "benzin" in key_lower or "diesel" in key_lower:
            listing.fahrzeug.kraftstoffart = value
        elif "getriebe" in key_lower or "schaltung" in key_lower:
            listing.fahrzeug.getriebe = value
        elif "fahrzeugtyp" in key_lower or "karosserie" in key_lower:
            listing.fahrzeug.fahrzeugtyp = value
        elif "türen" in key_lower or "tueren" in key_lower:
            listing.fahrzeug.anzahl_tueren = value
        elif "farbe" in key_lower and "außen" in key_lower:
            listing.fahrzeug.aussenfarbe = value
        elif "innenausstattung" in key_lower:
            listing.fahrzeug.material_innenausstattung = value
        elif "hu" in key_lower or "tüv" in key_lower or "tuev" in key_lower:
            listing.fahrzeug.hu_bis = value
        elif "umweltplakette" in key_lower or "plakette" in key_lower:
            listing.fahrzeug.umweltplakette = value
        elif "schadstoff" in key_lower or "emission" in key_lower:
            listing.fahrzeug.schadstoffklasse = value
        elif "zustand" in key_lower or "unfall" in key_lower:
            listing.fahrzeug.fahrzeugzustand = value
    
    # Extract equipment list
    listing.fahrzeug.ausstattung = extract_equipment(soup)
    
    # Anzeige Information
    # Extract listing ID from URL or page
    id_match = re.search(r'/(\d+)-\d+-\d+$', url)
    if id_match:
        listing.anzeige.anzeige_id = id_match.group(1)
    
    # Count images
    listing.anzeige.bilder = len(listing.fahrzeug.images)
    
    # Extract view count
    view_text = extract_text(soup, "#viewad-cntr-num")
    if view_text:
        view_match = re.search(r'\d+', view_text)
        if view_match:
            listing.anzeige.aufrufe = int(view_match.group())
    
    # Extract category
    breadcrumb = soup.select(".breadcrump a")
    if breadcrumb:
        categories = [a.get_text(strip=True) for a in breadcrumb if a.get_text(strip=True)]
        if len(categories) > 1:
            listing.anzeige.kategorie = " > ".join(categories[1:])
    
    # Verkaeufer Information
    listing.verkaeufer.name = extract_text(soup, "#viewad-contact a[href*='/s-bestandsliste.html']")
    
    # Extract location
    location = extract_text(soup, "#viewad-locality")
    if location:
        listing.verkaeufer.ort = location
        # Extract city name
        city_match = re.search(r'(\w+)$', location)
        if city_match:
            listing.verkaeufer.Stadt = city_match.group(1)
    
    # Extract seller type (Private/Commercial)
    seller_type_elem = soup.select_one("#viewad-contact-box")
    if seller_type_elem:
        text = seller_type_elem.get_text()
        if "Gewerblich" in text or "Händler" in text:
            listing.verkaeufer.nutzertyp = "Gewerblicher Nutzer"
        else:
            listing.verkaeufer.nutzertyp = "Privater Nutzer"
    
    # Extract member since
    member_since = extract_text(soup, "#viewad-contact-box span[class*='userbadges']")
    if member_since:
        date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', member_since)
        if date_match:
            listing.verkaeufer.aktiv_seit = date_match.group()
    
    # Extract user ID
    user_link = soup.select_one("#viewad-contact a[href*='/s-bestandsliste.html']")
    if user_link:
        href = user_link.get('href', '')
        userid_match = re.search(r'/(\d+)$', href)
        if userid_match:
            listing.verkaeufer.userid = userid_match.group(1)
    
    return listing


def prompt_for_url() -> str:
    try:
        return input("Ebay Kleinanzeigen URL'sini giriniz: ").strip()
    except EOFError:
        raise ScraperError("No URL provided.")


def save_to_json(listings: List[Listing], output_path: Path) -> None:
    data = [asdict(listing) for listing in listings]
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
