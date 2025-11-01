"""Parser for eBay Kleinanzeigen listing HTML using the standard library."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from html.parser import HTMLParser
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union


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


def _normalize_attr(value: str) -> str:
    return value.strip().lower()


def _attr_tokens(value: str) -> List[str]:
    normalized = _normalize_attr(value)
    return [token for token in re.split(r"[\s,;:/_-]+", normalized) if token]


def _attr_matches(value: Optional[str], expected: str) -> bool:
    if not value:
        return False
    normalized = _normalize_attr(value)
    expected_norm = expected.strip().lower()
    if not expected_norm:
        return False
    if normalized == expected_norm:
        return True
    if expected_norm in normalized:
        return True
    tokens = _attr_tokens(value)
    return expected_norm in tokens


def _iter_nodes(root: Node, tags: Optional[Sequence[str]] = None) -> Iterator[Node]:
    for node in root.iter():
        if tags and node.tag not in tags:
            continue
        yield node


def _find_first_by_attr(
    root: Node,
    attr: str,
    values: Sequence[str],
    tags: Optional[Sequence[str]] = None,
) -> Optional[Node]:
    for node in _iter_nodes(root, tags):
        attr_value = node.attrs.get(attr)
        if attr_value and any(_attr_matches(attr_value, value) for value in values):
            return node
    return None


def _find_all_by_attr(
    root: Node,
    attr: str,
    values: Sequence[str],
    tags: Optional[Sequence[str]] = None,
) -> List[Node]:
    matches: List[Node] = []
    for node in _iter_nodes(root, tags):
        attr_value = node.attrs.get(attr)
        if attr_value and any(_attr_matches(attr_value, value) for value in values):
            matches.append(node)
    return matches


def _extract_text_by_attr(
    root: Node,
    attr: str,
    values: Sequence[str],
    tags: Optional[Sequence[str]] = None,
) -> Optional[str]:
    node = _find_first_by_attr(root, attr, values, tags)
    if node:
        text = _clean(node.get_text())
        if not text:
            content = node.attrs.get("content")
            text = _clean(content)
        if text:
            return text
    return None


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


_CURRENCY_SYMBOLS = {
    "EUR": "€",
    "EURO": "€",
    "USD": "$",
    "GBP": "£",
}


def _normalize_currency(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    upper = cleaned.upper()
    symbol = _CURRENCY_SYMBOLS.get(upper)
    if symbol:
        return symbol
    if len(cleaned) == 1:
        return cleaned
    return cleaned


_COUNTRY_NAMES = {
    "DE": "Deutschland",
    "GERMANY": "Deutschland",
    "AT": "Österreich",
    "AUSTRIA": "Österreich",
    "CH": "Schweiz",
    "SWITZERLAND": "Schweiz",
}


def _normalize_country(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    mapped = _COUNTRY_NAMES.get(cleaned.upper())
    return mapped or cleaned


_SELLER_TYPE_MAP = {
    "ORGANIZATION": "Gewerblich",
    "ORGANISATION": "Gewerblich",
    "BUSINESS": "Gewerblich",
    "PRIVATE": "Privat",
    "PERSON": "Privat",
}


def _normalize_seller_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    mapped = _SELLER_TYPE_MAP.get(cleaned.upper())
    return mapped or cleaned


def _extract_meta_content(html: str, names: Sequence[str]) -> Optional[str]:
    for name in names:
        pattern = (
            r'<meta[^>]*(?:name|property)=["\']{name}["\'][^>]*content=["\']([^"\']+)["\']'
        ).format(name=re.escape(name))
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            content = _clean(match.group(1))
            if content:
                return content
    return None


def _strip_json_trailing(text: str) -> str:
    text = text.strip()
    if text.startswith("<!--") and text.endswith("-->"):
        text = text[4:-3].strip()
    if text.endswith(";"):
        text = text[:-1].strip()
    return text


def _parse_structured_data(html: str) -> List[dict]:
    blocks: List[dict] = []
    script_pattern = re.compile(r"<script([^>]*)>(.*?)</script>", flags=re.DOTALL | re.IGNORECASE)
    for attrs, content in script_pattern.findall(html):
        attr_text = attrs.lower()
        should_parse = False
        if "application/ld+json" in attr_text or "application/json" in attr_text:
            should_parse = True
        if "__next_data__" in attr_text or "__nuxt__" in attr_text:
            should_parse = True
        if not should_parse:
            continue
        cleaned = _strip_json_trailing(content)
        if not cleaned:
            continue
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            cleaned = cleaned.replace("}\n{", "},{")
            if not cleaned.startswith("["):
                cleaned = f"[{cleaned}]"
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict):
            blocks.append(data)
        elif isinstance(data, list):
            blocks.extend([item for item in data if isinstance(item, dict)])

    pattern_state = re.compile(
        r"window\.__(?:NUXT|INITIAL_STATE|APP_STATE|NEXT_DATA)__\s*=\s*({.*?})\s*;",
        flags=re.DOTALL,
    )
    for match in pattern_state.finditer(html):
        text = _strip_json_trailing(match.group(1))
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            blocks.append(data)

    return blocks


def _search_json(block: Union[dict, list], key: str) -> Iterator[object]:
    if isinstance(block, dict):
        for k, value in block.items():
            if k == key:
                yield value
            yield from _search_json(value, key)
    elif isinstance(block, list):
        for item in block:
            yield from _search_json(item, key)


def _extract_from_data_blocks(blocks: List[dict], keys: Sequence[str]) -> Optional[str]:
    for block in blocks:
        for key in keys:
            for value in _search_json(block, key):
                if isinstance(value, (str, int, float)):
                    text = _clean(str(value))
                    if text:
                        return text
                if isinstance(value, dict):
                    for nested_key in ("value", "text", "amount", "label"):
                        nested_value = value.get(nested_key)
                        if isinstance(nested_value, (str, int, float)):
                            text = _clean(str(nested_value))
                            if text:
                                return text
    return None


def _extract_number_from_blocks(blocks: List[dict], keys: Sequence[str]) -> Optional[float]:
    for block in blocks:
        for key in keys:
            for value in _search_json(block, key):
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    cleaned = _clean(value)
                    if cleaned and re.search(r"\d", cleaned):
                        cleaned = cleaned.replace(".", "").replace(",", ".")
                        try:
                            return float(cleaned)
                        except ValueError:
                            continue
                if isinstance(value, dict):
                    for nested_key in ("amount", "value", "price"):
                        nested_value = value.get(nested_key)
                        if isinstance(nested_value, (int, float)):
                            return float(nested_value)
                        if isinstance(nested_value, str):
                            cleaned = _clean(nested_value)
                            if cleaned and re.search(r"\d", cleaned):
                                cleaned = cleaned.replace(".", "").replace(",", ".")
                                try:
                                    return float(cleaned)
                                except ValueError:
                                    continue
    return None


def _extract_list_from_blocks(blocks: List[dict], keys: Sequence[str]) -> List[str]:
    results: List[str] = []
    seen: set[str] = set()
    for block in blocks:
        for key in keys:
            for value in _search_json(block, key):
                items: Iterable[str] = []
                if isinstance(value, list):
                    items = value
                elif isinstance(value, dict):
                    nested = value.get("values") or value.get("images")
                    if isinstance(nested, list):
                        items = nested
                    elif "url" in value and isinstance(value["url"], str):
                        items = [value["url"]]
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            candidate = item.get("url") or item.get("value") or item.get("text")
                            if isinstance(candidate, str):
                                candidate = _clean(candidate)
                                if candidate and candidate not in seen:
                                    seen.add(candidate)
                                    results.append(candidate)
                        elif isinstance(item, str):
                            candidate = _clean(item)
                            if candidate and candidate not in seen:
                                seen.add(candidate)
                                results.append(candidate)
                elif isinstance(value, str):
                    candidate = _clean(value)
                    if candidate and candidate not in seen:
                        seen.add(candidate)
                        results.append(candidate)
    return results




def _extract_from_json_ld(blocks: List[dict], *keys: str) -> Optional[str]:
    for block in blocks:
        current = block
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                break
        else:
            if isinstance(current, (str, int, float)):
                return _clean(str(current))
            if isinstance(current, list) and current:
                for item in current:
                    if isinstance(item, (str, int, float)):
                        text = _clean(str(item))
                        if text:
                            return text
                    if isinstance(item, dict):
                        for nested_key in ("value", "@value", "text", "name"):
                            nested_value = item.get(nested_key)
                            if isinstance(nested_value, (str, int, float)):
                                text = _clean(str(nested_value))
                                if text:
                                    return text
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


def _extract_attributes(root: Node, data_blocks: List[dict]) -> Dict[str, str]:
    attributes: Dict[str, str] = {}

    def _store(label: Optional[str], value: Optional[str]) -> None:
        if not label or not value:
            return
        attributes[label] = value

    for dl in root.find_all(tag="dl"):
        labels = [child for child in dl.children if child.tag == "dt"]
        values = [child for child in dl.children if child.tag == "dd"]
        if labels and values and len(labels) == len(values):
            for label, value in zip(labels, values):
                label_text = _clean(label.get_text())
                value_text = _clean(value.get_text())
                _store(label_text, value_text)

    for table in root.find_all(tag="table"):
        for row in table.children:
            if row.tag != "tr":
                continue
            cells = [child for child in row.children if child.tag in {"td", "th"}]
            if len(cells) >= 2:
                label = _clean(cells[0].get_text())
                value = _clean(cells[1].get_text())
                _store(label, value)

    for container in _iter_nodes(root, ("ul", "ol", "div", "section")):
        descriptor = " ".join(
            filter(
                None,
                [
                    container.attrs.get("data-testid"),
                    container.attrs.get("id"),
                    container.attrs.get("class"),
                ],
            )
        ).lower()
        if any(keyword in descriptor for keyword in ("attribute", "detail", "spec", "keyfact", "feature")):
            for child in container.iter():
                if child.tag not in {"li", "p", "div", "span"}:
                    continue
                text = _clean(child.get_text())
                if not text or ":" not in text:
                    continue
                label, value = text.split(":", 1)
                _store(_clean(label), _clean(value))

    for block in data_blocks:
        for key in ("additionalProperty", "attributes", "features"):
            for value in _search_json(block, key):
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            label = _clean(
                                item.get("name")
                                or item.get("label")
                                or item.get("title")
                                or item.get("key")
                            )
                            val = item.get("value")
                            if isinstance(val, (str, int, float)):
                                value_text = _clean(str(val))
                            elif isinstance(val, dict):
                                value_text = _clean(
                                    val.get("text")
                                    or val.get("value")
                                    or val.get("label")
                                )
                            else:
                                value_text = None
                            _store(label, value_text)
    return attributes


def _extract_images(root: Node, data_blocks: List[dict]) -> List[str]:
    urls: List[str] = []
    for img in root.find_all(tag="img"):
        for attr in ("data-src", "src"):
            url = img.attrs.get(attr)
            if url and url not in urls:
                urls.append(url)
    if urls:
        return urls
    urls.extend(_extract_list_from_blocks(data_blocks, ["image", "images", "media", "mediaUrls"]))
    deduped: List[str] = []
    seen: set[str] = set()
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def _extract_location(root: Node, data_blocks: List[dict]) -> Location:
    location = Location()
    address = root.find(attrs={"data-testid": "seller-address"})
    if not address:
        address = _find_first_by_attr(root, "itemtype", ["PostalAddress"], ("div", "address", "section"))
    if not address:
        address = _find_first_by_attr(root, "class", ["seller-address", "ad-address"], ("div", "address", "section"))
    if address:
        for child in address.iter():
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

    if not location.street or not location.city:
        node = _find_first_by_attr(
            root,
            "class",
            ["seller-address", "ad-address", "contact-address", "seller-location"],
            ("div", "p", "span"),
        )
        if node:
            text = _clean(node.get_text())
            if text and "\n" in text:
                parts = [part.strip() for part in text.split("\n") if part.strip()]
            else:
                parts = [part.strip() for part in text.split(",") if part.strip()]
            for part in parts:
                if re.match(r"\d{5}", part) and not location.postal_code:
                    tokens = part.split(" ", 1)
                    location.postal_code = tokens[0]
                    if len(tokens) > 1 and not location.city:
                        location.city = tokens[1]
                elif " - " in part and not location.city:
                    city_part, district_part = [p.strip() for p in part.split("-", 1)]
                    if city_part and not location.city:
                        location.city = city_part
                    if district_part and not location.district:
                        location.district = district_part
                elif not location.street:
                    location.street = part

    for field, keys in (
        ("street", ["streetAddress", "street"]),
        ("postal_code", ["postalCode", "zip"]),
        ("city", ["addressLocality", "city", "town"]),
        ("state", ["addressRegion", "state"]),
        ("district", ["district", "neighbourhood"]),
        ("country", ["addressCountry", "country"]),
    ):
        current_value = getattr(location, field)
        value = _extract_from_data_blocks(data_blocks, keys)
        if current_value:
            if field == "city" and value and "-" in current_value:
                setattr(location, field, value)
            continue
        if value:
            setattr(location, field, value)

    if location.latitude is None:
        lat = _extract_number_from_blocks(data_blocks, ["latitude", "lat"])
        if lat is not None:
            location.latitude = lat
    if location.longitude is None:
        lon = _extract_number_from_blocks(data_blocks, ["longitude", "lng", "lon"])
        if lon is not None:
            location.longitude = lon

    location.country = _normalize_country(location.country)

    return location


def _extract_seller(root: Node, data_blocks: List[dict]) -> Seller:
    seller = Seller()
    seller_node = root.find(attrs={"data-testid": "seller-info"})
    if not seller_node:
        seller_node = _find_first_by_attr(
            root,
            "class",
            ["seller-info", "seller-information", "seller-card", "userprofile-box", "seller-card__name"],
            ("section", "div", "article"),
        )
    if seller_node:
        name_text = _extract_text_by_attr(
            seller_node,
            "data-testid",
            ["seller-name", "profile-name"],
            ("a", "span", "div"),
        )
        if not name_text:
            name_text = _extract_text_by_attr(
                seller_node,
                "class",
                ["seller-card__name", "userprofile-name", "seller-name"],
                ("span", "div", "a"),
            )
        if name_text:
            seller.name = name_text
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
        seller.name = _extract_from_json_ld(data_blocks, "seller", "name") or _extract_from_data_blocks(
            data_blocks, ["sellerName", "vendorName"]
        )
    if not seller.seller_type:
        seller.seller_type = _extract_from_json_ld(data_blocks, "seller", "@type") or _extract_from_data_blocks(
            data_blocks, ["sellerType", "type"]
        )
    if not seller.phone:
        seller.phone = _extract_from_json_ld(data_blocks, "seller", "telephone") or _extract_from_data_blocks(
            data_blocks, ["sellerPhone", "telephone", "phone"]
        )
    if not seller.member_since:
        seller.member_since = _extract_from_data_blocks(data_blocks, ["memberSince", "sellerMemberSince"])
    seller.seller_type = _normalize_seller_type(seller.seller_type)
    return seller


def parse_listing(html: str) -> Listing:
    parser = DOMBuilder()
    parser.feed(html)
    root = parser.root
    data_blocks = _parse_structured_data(html)

    title = None
    dom_headline = _extract_text_by_attr(
        root,
        "data-testid",
        ["ad-title", "viewad-title", "ad-headline", "listing-title", "headline"],
        ("h1", "h2", "div", "span"),
    )
    title = dom_headline
    if not title:
        candidate = _extract_text_by_attr(root, "id", ["viewad-title", "ad-title", "title"], ("h1", "h2", "div", "span"))
        if candidate:
            if not dom_headline:
                dom_headline = candidate
            title = candidate
    if not title:
        candidate = _extract_text_by_attr(
            root, "class", ["ad-title", "ad-headline", "ad-headline__title", "headline"], ("h1", "h2", "div", "span")
        )
        if candidate:
            if not dom_headline:
                dom_headline = candidate
            title = candidate
    if not title:
        h1 = root.find(tag="h1")
        if h1:
            candidate = _clean(h1.get_text())
            if candidate:
                if not dom_headline:
                    dom_headline = candidate
                title = candidate
    if not title:
        title = _extract_meta_content(html, ["og:title", "twitter:title", "title"])

    structured_title = _extract_from_json_ld(data_blocks, "name") or _extract_from_data_blocks(
        data_blocks, ["title", "headline", "name"]
    )
    if not title and structured_title:
        title = structured_title
    elif title and structured_title:
        current_len = len(title)
        structured_len = len(structured_title)
        if structured_len > current_len or (
            "angebot" in title.lower() and structured_title.lower() not in title.lower()
        ):
            title = structured_title

    subtitle = _extract_text_by_attr(
        root,
        "data-testid",
        ["subtitle", "ad-subtitle", "subline"],
        ("p", "div", "span"),
    )
    if not subtitle:
        subtitle = _extract_text_by_attr(root, "class", ["ad-subtitle", "ad-headline__subtitle", "subtitle"], ("p", "div", "span"))
    if not subtitle and dom_headline and title and dom_headline != title:
        subtitle = dom_headline

    price_text = _extract_text_by_attr(
        root,
        "data-testid",
        ["price", "viewad-price", "price-amount", "price-value"],
        ("span", "div", "strong"),
    )
    if not price_text:
        price_text = _extract_text_by_attr(root, "class", ["ad-price__content", "price"] , ("span", "div", "strong"))
    if not price_text:
        price_text = _extract_text_by_attr(root, "itemprop", ["price"], ("span", "meta", "div"))
        if price_text is None:
            meta_amount = _extract_meta_content(html, ["product:price:amount", "og:price:amount"])
            meta_currency = _extract_meta_content(html, ["product:price:currency", "og:price:currency"])
            if meta_amount:
                price_text = f"{meta_amount} {meta_currency or ''}".strip()
    if not price_text:
        price_raw = _extract_from_json_ld(data_blocks, "offers", "price") or _extract_from_data_blocks(
            data_blocks, ["price", "priceValue", "amount"]
        )
        currency_value = _extract_from_json_ld(data_blocks, "offers", "priceCurrency") or _extract_from_data_blocks(
            data_blocks, ["currency", "priceCurrency", "currencyCode"]
        )
        if price_raw:
            currency_symbol = _normalize_currency(currency_value)
            price_raw_str = str(price_raw)
            if currency_symbol and currency_symbol not in price_raw_str:
                price_text = f"{price_raw_str} {currency_symbol}"
            else:
                price_text = price_raw_str
            if currency_symbol and not currency_value:
                currency_value = currency_symbol

    amount = currency = negotiable = None
    if price_text:
        amount, currency, negotiable = _parse_price_text(price_text)
    if not currency:
        currency = _extract_from_json_ld(data_blocks, "offers", "priceCurrency") or _extract_from_data_blocks(
            data_blocks, ["currency", "priceCurrency", "currencyCode"]
        )
    currency = _normalize_currency(currency)
    if amount is None:
        amount = _extract_number_from_blocks(data_blocks, ["price", "priceValue", "amount"])
    price = Price(amount=amount, currency=currency, raw=price_text, negotiable=negotiable)

    description = None
    description_source = None
    for values in (
        ["description-content"],
        ["viewad-description-text"],
        ["listing-description"],
        ["description"],
    ):
        candidate = _extract_text_by_attr(root, "data-testid", values, ("div", "section", "p"))
        if candidate:
            description = candidate
            description_source = "dom"
            break
    if not description:
        candidate = _extract_text_by_attr(root, "id", ["viewad-description-text", "ad-description"], ("div", "section"))
        if candidate:
            description = candidate
            description_source = "dom"
    if not description:
        candidate = _extract_text_by_attr(
            root, "class", ["description", "ad-description", "article-description"], ("div", "section", "p")
        )
        if candidate:
            description = candidate
            description_source = "dom"
    if not description:
        candidate = _extract_meta_content(html, ["og:description", "description", "twitter:description"])
        if candidate:
            description = candidate
            description_source = "meta"
    structured_description = _extract_from_json_ld(data_blocks, "description") or _extract_from_data_blocks(
        data_blocks, ["description", "body", "text"]
    )
    if structured_description:
        if not description or description_source == "meta":
            description = structured_description
            description_source = "structured"
        elif len(structured_description) > len(description):
            description = structured_description
            description_source = "structured"

    category_path = _extract_breadcrumbs(root)
    if not category_path:
        category_ld = _extract_from_json_ld(data_blocks, "category") or _extract_from_data_blocks(
            data_blocks, ["category", "categoryPath"]
        )
        if category_ld:
            if isinstance(category_ld, str):
                category_path = [part.strip() for part in category_ld.split(">") if part.strip()]
            else:
                category_path = [category_ld]

    attributes = _extract_attributes(root, data_blocks)

    ad_id = None
    ad_id_match = re.search(r"Anzeigennummer\s*:?\s*(\d+)", html)
    if ad_id_match:
        ad_id = ad_id_match.group(1)
    if not ad_id:
        ad_id = _extract_from_json_ld(data_blocks, "sku") or _extract_from_data_blocks(
            data_blocks, ["adId", "id", "classifiedId", "listingId"]
        )

    ad_type = None
    ad_type_match = re.search(r"Anzeigentyp\s*:?\s*([^<\n]+)", html)
    if ad_type_match:
        ad_type = _clean(ad_type_match.group(1))
    if not ad_type:
        ad_type = _extract_from_data_blocks(data_blocks, ["adType", "type"])

    posted_at = None
    posted_match = re.search(r"(Erstellungsdatum|Online seit|Eingestellt am)\s*:?\s*([^<\n]+)", html)
    if posted_match:
        posted_at = _clean(posted_match.group(2))
    if not posted_at:
        posted_at = _extract_from_data_blocks(data_blocks, ["created", "creationDate", "postedAt", "startTime"])

    last_updated = None
    updated_match = re.search(r"Aktualisiert am\s*:?\s*([^<\n]+)", html)
    if updated_match:
        last_updated = _clean(updated_match.group(1))
    if not last_updated:
        last_updated = _extract_from_data_blocks(
            data_blocks, ["modified", "lastUpdated", "updatedAt", "modificationDate"]
        )

    shipping = attributes.get("Versand") or attributes.get("Lieferung")
    shipping_node = root.find(attrs={"data-testid": "shipping"})
    if shipping_node:
        for child in shipping_node.iter():
            if child is shipping_node:
                continue
            if child.tag in {"p", "span", "dd", "li", "strong"}:
                candidate = _clean(child.get_text())
                if candidate:
                    shipping = candidate
                    break
        if not shipping:
            shipping_text = _clean(shipping_node.get_text())
            if shipping_text:
                if shipping_text.lower().startswith("versand:"):
                    shipping = shipping_text.split(":", 1)[1].strip()
                elif shipping_text.lower().startswith("versand") and len(shipping_text.split()) > 1:
                    shipping = shipping_text.split(" ", 1)[1].strip()
                else:
                    shipping = shipping_text.strip()
    if not shipping:
        shipping_match = re.search(r"Versand\s*:?\s*([^<\n]+)", html)
        if shipping_match:
            shipping_value = shipping_match.group(1).strip()
            shipping_value = shipping_value.strip(" '\",,")
            shipping = _clean(shipping_value)
    shipping_from_data = _extract_from_data_blocks(data_blocks, ["shipping", "delivery", "shippingOption"])
    if shipping_from_data:
        if not shipping or len(shipping_from_data) > len(shipping):
            shipping = shipping_from_data
    if shipping and shipping.lower().startswith("versand:"):
        shipping = shipping.split(":", 1)[1].strip()

    location = _extract_location(root, data_blocks)
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

    seller = _extract_seller(root, data_blocks)

    images = _extract_images(root, data_blocks)
    if not images:
        image_ld = _extract_from_json_ld(data_blocks, "image")
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
