"""Parser for eBay Kleinanzeigen listing HTML using the standard library."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass
class Node:
    tag: str
    attrs: Dict[str, str]
    text: str = ""
    children: List["Node"] = field(default_factory=list)
    parent: Optional["Node"] = None

    def add_child(self, child: "Node") -> None:
        child.parent = self
        self.children.append(child)

    def iter(self) -> Iterable["Node"]:
        yield self
        for child in self.children:
            yield from child.iter()

    def find(self, *, tag: Optional[str] = None, attrs: Optional[Dict[str, str]] = None) -> Optional["Node"]:
        for node in self.iter():
            if tag and node.tag != tag:
                continue
            if attrs:
                if not all(node.attrs.get(k) == v for k, v in attrs.items()):
                    continue
            return node
        return None

    def find_all(self, *, tag: Optional[str] = None, attrs: Optional[Dict[str, str]] = None) -> List["Node"]:
        matches: List[Node] = []
        for node in self.iter():
            if tag and node.tag != tag:
                continue
            if attrs:
                if not all(node.attrs.get(k) == v for k, v in attrs.items()):
                    continue
            matches.append(node)
        return matches

    def get_text(self) -> str:
        parts: List[str] = []

        def _collect(node: "Node") -> None:
            if node.text:
                parts.append(node.text)
            for child in node.children:
                _collect(child)

        _collect(self)
        text = " ".join(part.strip() for part in parts if part.strip())
        return text.strip()


class DOMBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self.stack: List[Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = {name: value for name, value in attrs if value is not None}
        node = Node(tag, attr_dict)
        self.stack[-1].add_child(node)
        # Self-closing tags should not remain on the stack.
        if tag not in {"br", "img", "meta", "link", "input", "hr", "source", "area", "base", "col", "embed", "param"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        # Pop elements until the corresponding start tag is removed.
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].text += data


@dataclass
class Price:
    amount: Optional[float]
    currency: Optional[str]
    raw: Optional[str]
    negotiable: Optional[bool]

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "amount": self.amount,
            "currency": self.currency,
            "raw": self.raw,
            "negotiable": self.negotiable,
        }


@dataclass
class Location:
    street: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "street": self.street,
            "postal_code": self.postal_code,
            "city": self.city,
            "state": self.state,
            "district": self.district,
            "country": self.country,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass
class Seller:
    name: Optional[str] = None
    seller_type: Optional[str] = None
    member_since: Optional[str] = None
    phone: Optional[str] = None
    commercial_register: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "name": self.name,
            "seller_type": self.seller_type,
            "member_since": self.member_since,
            "phone": self.phone,
            "commercial_register": self.commercial_register,
        }


@dataclass
class Listing:
    title: Optional[str]
    subtitle: Optional[str]
    description: Optional[str]
    price: Price
    category_path: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    ad_id: Optional[str] = None
    ad_type: Optional[str] = None
    posted_at: Optional[str] = None
    last_updated: Optional[str] = None
    shipping: Optional[str] = None
    location: Location = field(default_factory=Location)
    seller: Seller = field(default_factory=Seller)
    images: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "description": self.description,
            "price": self.price.to_dict(),
            "category_path": self.category_path,
            "attributes": self.attributes,
            "ad_id": self.ad_id,
            "ad_type": self.ad_type,
            "posted_at": self.posted_at,
            "last_updated": self.last_updated,
            "shipping": self.shipping,
            "location": self.location.to_dict(),
            "seller": self.seller.to_dict(),
            "images": self.images,
        }


def _clean(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = " ".join(text.strip().split())
    return cleaned or None


def _parse_price_text(text: str) -> Tuple[Optional[float], Optional[str], Optional[bool]]:
    currency_match = re.search(r"(€|EUR|CHF|\$)", text)
    currency = currency_match.group(1) if currency_match else None
    amount_match = re.search(r"(\d+[\d.,]*)", text)
    amount = None
    if amount_match:
        amount_str = amount_match.group(1).replace(".", "").replace(",", ".")
        try:
            amount = float(amount_str)
        except ValueError:
            amount = None
    negotiable = None
    if re.search(r"\bVB\b|Verhandlungsbasis", text, re.IGNORECASE):
        negotiable = True
    elif re.search(r"Festpreis", text, re.IGNORECASE):
        negotiable = False
    return amount, currency, negotiable


def _parse_json_ld(html: str) -> List[dict]:
    scripts = re.findall(
        r"<script[^>]*type=\"application/ld\+json\"[^>]*>(.*?)</script>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    blocks: List[dict] = []
    for script in scripts:
        content = script.strip()
        if not content:
            continue
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            cleaned = content.replace("}\n{", "},{")
            try:
                data = json.loads(f"[{cleaned}]")
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict):
            blocks.append(data)
        elif isinstance(data, list):
            blocks.extend([item for item in data if isinstance(item, dict)])
    return blocks


def _extract_from_json_ld(blocks: List[dict], *keys: str) -> Optional[str]:
    for block in blocks:
        current = block
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                break
        else:
            if isinstance(current, str):
                return _clean(current)
            if isinstance(current, list) and current and isinstance(current[0], str):
                return _clean(current[0])
    return None


def _extract_breadcrumbs(root: Node) -> List[str]:
    category_path: List[str] = []
    for nav in root.find_all(tag="nav"):
        aria = nav.attrs.get("aria-label", "")
        if "breadcrumb" in aria.lower():
            for item in nav.iter():
                if item.tag in {"a", "span"}:
                    text = _clean(item.get_text())
                    if text:
                        category_path.append(text)
            break
    return category_path


def _extract_attributes(root: Node) -> Dict[str, str]:
    attributes: Dict[str, str] = {}
    for dl in root.find_all(tag="dl"):
        entries: List[Tuple[Optional[str], Optional[str]]] = []
        labels = [child for child in dl.children if child.tag == "dt"]
        values = [child for child in dl.children if child.tag == "dd"]
        if labels and values and len(labels) == len(values):
            for label, value in zip(labels, values):
                label_text = _clean(label.get_text())
                value_text = _clean(value.get_text())
                if label_text and value_text:
                    attributes[label_text] = value_text
    if attributes:
        return attributes
    for table in root.find_all(tag="table"):
        for row in table.children:
            if row.tag != "tr":
                continue
            cells = [child for child in row.children if child.tag in {"td", "th"}]
            if len(cells) >= 2:
                label = _clean(cells[0].get_text())
                value = _clean(cells[1].get_text())
                if label and value:
                    attributes[label] = value
    return attributes


def _extract_images(root: Node) -> List[str]:
    urls: List[str] = []
    for img in root.find_all(tag="img"):
        for attr in ("data-src", "src"):
            url = img.attrs.get(attr)
            if url and url not in urls:
                urls.append(url)
    return urls


def _extract_location(root: Node) -> Location:
    location = Location()
    address = root.find(attrs={"data-testid": "seller-address"})
    if address:
        for child in address.children:
            itemprop = child.attrs.get("itemprop")
            text = _clean(child.get_text())
            if not text:
                continue
            if itemprop == "streetAddress":
                location.street = text
            elif itemprop == "postalCode":
                location.postal_code = text
            elif itemprop == "addressLocality":
                location.city = text
            elif itemprop == "addressRegion":
                location.state = text
            elif itemprop == "addressCountry":
                location.country = text
    city_node = root.find(attrs={"data-testid": "location-city"})
    if city_node and not location.city:
        location.city = _clean(city_node.get_text())
    return location


def _extract_seller(root: Node, json_ld_blocks: List[dict]) -> Seller:
    seller = Seller()
    seller_node = root.find(attrs={"data-testid": "seller-info"})
    if seller_node:
        name_node = seller_node.find(attrs={"data-testid": "seller-name"})
        if name_node:
            seller.name = _clean(name_node.get_text())
        else:
            seller.name = _clean(seller_node.get_text())
        text = seller_node.get_text()
        type_match = re.search(r"\b(Privat|Gewerblich)\b", text)
        if type_match:
            seller.seller_type = type_match.group(1)
        member_match = re.search(r"(Mitglied seit\s*\d{4}|seit\s*\d{4})", text)
        if member_match:
            seller.member_since = member_match.group(1)
        phone_match = re.search(r"(?:Telefon|Tel\.)\s*:?\s*(\+?[0-9 /-]+)", text)
        if phone_match:
            seller.phone = phone_match.group(1).strip()
    if not seller.name:
        seller.name = _extract_from_json_ld(json_ld_blocks, "seller", "name")
    if not seller.seller_type:
        seller.seller_type = _extract_from_json_ld(json_ld_blocks, "seller", "@type")
    if not seller.phone:
        seller.phone = _extract_from_json_ld(json_ld_blocks, "seller", "telephone")
    return seller


def parse_listing(html: str) -> Listing:
    parser = DOMBuilder()
    parser.feed(html)
    root = parser.root
    json_ld_blocks = _parse_json_ld(html)

    title = None
    for test_id in ("ad-title", "viewad-title"):
        node = root.find(attrs={"data-testid": test_id})
        if node:
            title = _clean(node.get_text())
            break
    if not title:
        h1 = root.find(tag="h1")
        if h1:
            title = _clean(h1.get_text())
    if not title:
        title = _extract_from_json_ld(json_ld_blocks, "name")

    subtitle = None
    for test_id in ("subtitle", "ad-subtitle"):
        node = root.find(attrs={"data-testid": test_id})
        if node:
            subtitle = _clean(node.get_text())
            break

    price_text = None
    for test_id in ("price", "viewad-price"):
        node = root.find(attrs={"data-testid": test_id})
        if node:
            price_text = _clean(node.get_text())
            break
    if not price_text:
        price_text = _extract_from_json_ld(json_ld_blocks, "offers", "price")
        if price_text and _extract_from_json_ld(json_ld_blocks, "offers", "priceCurrency"):
            price_text = f"{price_text} {_extract_from_json_ld(json_ld_blocks, 'offers', 'priceCurrency')}"

    amount = currency = negotiable = None
    if price_text:
        amount, currency, negotiable = _parse_price_text(price_text)
    if not currency:
        currency = _extract_from_json_ld(json_ld_blocks, "offers", "priceCurrency")
    price = Price(amount=amount, currency=currency, raw=price_text, negotiable=negotiable)

    description = None
    for test_id in ("description-content", "viewad-description-text"):
        node = root.find(attrs={"data-testid": test_id})
        if node:
            description = _clean(node.get_text())
            break
    if not description:
        description = _extract_from_json_ld(json_ld_blocks, "description")

    category_path = _extract_breadcrumbs(root)
    if not category_path:
        category_ld = _extract_from_json_ld(json_ld_blocks, "category")
        if category_ld:
            category_path = [part.strip() for part in category_ld.split(">") if part.strip()]

    attributes = _extract_attributes(root)

    ad_id = None
    ad_id_match = re.search(r"Anzeigennummer\s*:?\s*(\d+)", html)
    if ad_id_match:
        ad_id = ad_id_match.group(1)

    ad_type = None
    ad_type_match = re.search(r"Anzeigentyp\s*:?\s*([^<\n]+)", html)
    if ad_type_match:
        ad_type = _clean(ad_type_match.group(1))

    posted_at = None
    posted_match = re.search(r"(Erstellungsdatum|Online seit|Eingestellt am)\s*:?\s*([^<\n]+)", html)
    if posted_match:
        posted_at = _clean(posted_match.group(2))

    last_updated = None
    updated_match = re.search(r"Aktualisiert am\s*:?\s*([^<\n]+)", html)
    if updated_match:
        last_updated = _clean(updated_match.group(1))

    shipping = None
    shipping_node = root.find(attrs={"data-testid": "shipping"})
    if shipping_node:
        shipping_text = _clean(shipping_node.get_text())
        if shipping_text:
            shipping = shipping_text.replace("Versand", "", 1).strip(" :") or shipping_text
    if not shipping:
        shipping_match = re.search(r"Versand\s*:?\s*([^<\n]+)", html)
        if shipping_match:
            shipping = _clean(shipping_match.group(1))

    location = _extract_location(root)
    lat_match = re.search(r'meta[^>]*property="og:latitude"[^>]*content="([^"]+)"', html)
    if lat_match:
        try:
            location.latitude = float(lat_match.group(1))
        except ValueError:
            pass
    lon_match = re.search(r'meta[^>]*property="og:longitude"[^>]*content="([^"]+)"', html)
    if lon_match:
        try:
            location.longitude = float(lon_match.group(1))
        except ValueError:
            pass

    seller = _extract_seller(root, json_ld_blocks)

    images = _extract_images(root)
    if not images:
        image_ld = _extract_from_json_ld(json_ld_blocks, "image")
        if image_ld:
            images = [image_ld]

    return Listing(
        title=title,
        subtitle=subtitle,
        description=description,
        price=price,
        category_path=category_path,
        attributes=attributes,
        ad_id=ad_id,
        ad_type=ad_type,
        posted_at=posted_at,
        last_updated=last_updated,
        shipping=shipping,
        location=location,
        seller=seller,
        images=images,
    )
