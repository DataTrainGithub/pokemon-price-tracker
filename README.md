# Pokémon Sealed Product Price Tracker

A local Streamlit dashboard that tracks prices of Pokémon sealed products
(ETBs, UPCs, SPCs) scraped from Cardmarket, filtered to
Belgium / Netherlands / Germany sellers with English-only listings.

## Structure

```
pokemon-investment-tracker/
├── .streamlit/
│   └── config.toml             # light theme (prevents dark-mode flicker)
├── data/
│   ├── products.json           # historical comps + active watchlist
│   └── price_history.csv       # timestamped price log (auto-generated)
├── scraper/
│   └── cardmarket_scraper.py   # fetches prices & offers from Cardmarket
├── app.py                      # Streamlit dashboard
└── requirements.txt
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
streamlit run app.py
```

## Refreshing prices

Click **Refresh Prices** in the dashboard header, or run the scraper directly:

```bash
python scraper/cardmarket_scraper.py
```

This updates `data/products.json` with the latest prices and appends a row
to `data/price_history.csv`. Schedule it every few days (cron / Task
Scheduler) to build a price history over time.

## Adding products

Add entries to `"historical_comps"` (OOP sets) or `"watchlist"` (active)
in `data/products.json`:

```json
{
  "id": "some-new-etb",
  "name": "Some New Elite Trainer Box",
  "type": "ETB",
  "release_date": "2026-09-01",
  "msrp_eur": 49.99,
  "reprint_status": "standard_rotation",
  "months_to_oop": 6,
  "tags": ["chase_card_hype"],
  "cardmarket_url": "https://www.cardmarket.com/en/Pokemon/Products/Elite-Trainer-Boxes/..."
}
```

## Moving sets to historical

When a watchlist set goes OOP and its price settles, move it from
`"watchlist"` into `"historical_comps"` and set `"oop_date"` — it will
then appear in the **Historical ROI** tab.
