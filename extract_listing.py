"""Command line interface for converting eBay Kleinanzeigen HTML listings to JSON."""
from __future__ import annotations

import json
from pathlib import Path

from scraper.parser import parse_listing


def main() -> None:
    html_path_str = input("Pfad zur HTML-Datei: ").strip()
    if not html_path_str:
        raise SystemExit("Es wurde kein Dateiname eingegeben.")

    path = Path(html_path_str)
    if not path.exists():
        raise SystemExit(f"Datei '{path}' wurde nicht gefunden.")

    html = path.read_text(encoding="utf-8")
    listing = parse_listing(html)
    print(json.dumps(listing.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
