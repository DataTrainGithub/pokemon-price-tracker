# Pokémon Sealed Product Price Tracker

A Streamlit dashboard that tracks prices of Pokémon sealed products
(ETBs, UPCs, SPCs) scraped from Cardmarket, filtered to
Belgium / Netherlands / Germany sellers with English-only listings.
Deployed on Streamlit Cloud; prices are updated daily via an automated local
Windows Task Scheduler job that scrapes, commits, and pushes `products.json`.

## Structure

```
pokemon-investment-tracker/
├── .github/
│   └── workflows/
│       └── update-prices.yml   # GitHub Actions fallback (datacenter IPs, may 403)
├── .streamlit/
│   └── config.toml             # light theme (prevents dark-mode flicker)
├── data/
│   ├── products.json           # historical comps + active watchlist (auto-updated)
│   ├── price_history.csv       # timestamped price log
│   └── images/                 # locally cached product images
├── scraper/
│   └── cardmarket_scraper.py   # fetches prices & offers from Cardmarket
├── run_scraper.ps1             # wrapper: scrape → log → git commit & push
├── app.py                      # Streamlit dashboard
└── requirements.txt
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## How prices are updated

Prices are refreshed automatically every night via **Windows Task Scheduler**
(`PokemonPriceUpdater` task, 03:00 local time). The task runs `run_scraper.ps1`
which:
1. Runs `scraper/cardmarket_scraper.py` (skips products fresher than 6 hours)
2. Appends output to `scraper_run.log`
3. Commits and pushes `data/products.json` to GitHub if anything changed
4. Streamlit Cloud detects the push and redeploys automatically

**Check the log after a run:**
```powershell
Get-Content scraper_run.log -Tail 30
```

**Trigger manually:**
```powershell
Start-ScheduledTask -TaskName "PokemonPriceUpdater"
# or run directly:
.venv\Scripts\python.exe scraper/cardmarket_scraper.py
```

> **Note on Cloudflare:** Cardmarket uses Cloudflare WAF. The scraper uses
> `curl_cffi` with Chrome TLS impersonation to bypass it. Bulk requests from
> datacenter IPs (GitHub Actions) are blocked with 403; home IPs work reliably.
> The GitHub Actions workflow (`update-prices.yml`) runs as a fallback but
> may only partially succeed.

## Re-registering the scheduled task

If the task is lost (e.g. after a Windows reinstall), re-register it:

```powershell
$p = "$PWD"
$ps = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$action   = New-ScheduledTaskAction -Execute $ps `
              -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$p\run_scraper.ps1`"" `
              -WorkingDirectory $p
$trigger  = New-ScheduledTaskTrigger -Daily -At "03:00AM"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName "PokemonPriceUpdater" `
  -Action $action -Trigger $trigger -Settings $settings -Force
```

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
