# Scraper-Ebay

Dieses Repository enthält ein kleines Hilfsprogramm, das den HTML-Code einer
[eBay Kleinanzeigen](https://www.kleinanzeigen.de/)-Anzeige in eine strukturierte
JSON-Repräsentation überführt. Ein Beispiel-Listing (`examples/Ebay-Beispiel.html`)
und die dazugehörige JSON-Ausgabe (`examples/JSON_Beispiel.json`) sind beigelegt.

## Verwendung

1. Stelle sicher, dass sich der HTML-Quelltext der Anzeige lokal als Datei
   befindet (z. B. durch Speichern der Seite im Browser mit "Seite speichern unter…").
2. Führe das Skript aus:

   ```bash
   python extract_listing.py
   ```

3. Gib den Pfad zur HTML-Datei ein. Das Programm liest die Datei ein, extrahiert
   die wichtigsten Informationen und gibt die JSON-Struktur auf `stdout` aus.

```bash
$ python extract_listing.py
Pfad zur HTML-Datei: examples/Ebay-Beispiel.html
{
  "title": "Proxxon PD 230/E Drehbank",
  "subtitle": "Mit umfangreichem Zubehör",
  ...
}
```

Die extrahierten Felder umfassen unter anderem Titel, Preis, Beschreibung,
Kategoriepfad, Anzeigen- und Verkäuferdaten sowie eine Liste gefundener Bilder.

### Python-Version & Abhängigkeiten

Das Skript setzt lediglich auf Standardbibliotheken von Python ≥ 3.10 und kommt
ohne zusätzliche Pakete aus.

## Aufbau

- `extract_listing.py`: Kommandozeilen-Schnittstelle zum Einlesen einer HTML-Datei
  und Ausgeben der JSON-Daten.
- `scraper/parser.py`: Parser-Logik, die mit Hilfe eines einfachen DOM-Baums die
  relevanten Informationen aus dem HTML extrahiert.
- `examples/`: Enthält Beispiel-HTML sowie die erwartete JSON-Ausgabe.
  Neben dem Referenzpaar (`Ebay-Beispiel.html`/`JSON_Beispiel.json`) sind
  zusätzliche Varianten (`deneme1.html`, `deneme2.html`, `deneme3.html`)
  hinterlegt, die unterschiedliche Strukturmerkmale realer Inserate
  abdecken und zur manuellen Validierung des Parsers genutzt werden
  können.

## Tests

Zum manuellen Abgleich des Parsers mit dem Beispiel kann das kleine Skript unter
halb genutzt werden:

```bash
python - <<'PY'
import json
from scraper.parser import parse_listing
from pathlib import Path

html = Path('examples/Ebay-Beispiel.html').read_text(encoding='utf-8')
parsed = parse_listing(html).to_dict()
reference = json.loads(Path('examples/JSON_Beispiel.json').read_text(encoding='utf-8'))
print(parsed == reference)
PY
```

Die Ausgabe `True` bestätigt, dass der Parser die erwartete JSON-Struktur
liefert.
