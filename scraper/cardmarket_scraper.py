"""
cardmarket_scraper.py

Scrapes Pokemon sealed-product data from Cardmarket.

Importable functions (used by app.py):
  create_session()                      -> session object
  search_cardmarket(session, query)     -> list[dict]  (name, url, from_eur, image_url)
  fetch_product_data(session, url, ...) -> dict        (name, image_url, prices, prices_filtered)
  update_all_products(...)              -> int         (updated count)

Constants:
  TARGET_COUNTRIES   list[int]  – Belgium(2), Germany(3), Netherlands(18)
  LANGUAGE_IDS       dict[str, int]

CLI:
  python scraper/cardmarket_scraper.py                       # update all products
  python scraper/cardmarket_scraper.py --search "Prismatic Evolutions ETB"
  python scraper/cardmarket_scraper.py --url "https://www.cardmarket.com/..."
  python scraper/cardmarket_scraper.py --no-filter           # skip BE/DE/NL filter
"""

import argparse
import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Session: curl_cffi (Chrome TLS fingerprint) → cloudscraper → plain requests
# ---------------------------------------------------------------------------
def create_session():
    """
    Build an HTTP session that can bypass Cardmarket's Cloudflare protection.
    Strategy:
      1. Use curl_cffi with Chrome impersonation (best TLS fingerprint match)
      2. Fall back to cloudscraper
      3. Fall back to plain requests
    After creating the session, warms up with the Cardmarket homepage to
    acquire cookies (PHPSESSID, __cf_bm, _cfuvid) before product-page requests.
    """
    sess = None
    _is_cffi = False
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore
        # chrome131 has the best Cloudflare bypass record in curl_cffi 0.15+
        sess = cffi_requests.Session(impersonate="chrome131")
        _is_cffi = True
        print("  [session] using curl_cffi (chrome131 impersonation)")
    except ImportError:
        pass

    if sess is None:
        try:
            import cloudscraper  # type: ignore
            sess = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            print("  [session] using cloudscraper")
        except ImportError:
            pass

    if sess is None:
        import requests as _req
        sess = _req.Session()
        sess.headers.update(_HEADERS)
        print("  [session] using plain requests")

    # Warm up: get the homepage to acquire Cloudflare cookies.
    # IMPORTANT: do NOT pass custom headers to curl_cffi — it manages its own
    # headers as part of the Chrome TLS fingerprint. Overriding them breaks it.
    try:
        if _is_cffi:
            r = sess.get(BASE_URL, timeout=20)
        else:
            r = sess.get(BASE_URL, headers=_HEADERS, timeout=20)
        print(f"  [session] warmup status: {r.status_code}")
    except Exception as exc:
        print(f"  [session] warmup failed: {exc}")
    time.sleep(1)  # brief settle so cookies are registered before first product request
    return sess


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR      = Path(__file__).parent.parent / "data"
IMAGES_DIR    = DATA_DIR / "images"
PRODUCTS_PATH = DATA_DIR / "products.json"
HISTORY_PATH  = DATA_DIR / "price_history.csv"

IMAGES_DIR.mkdir(exist_ok=True)

BASE_URL = "https://www.cardmarket.com/en/Pokemon"

# Cardmarket internal country IDs
COUNTRY_IDS = {
    "Austria": 1, "Belgium": 2, "Spain": 4,
    "France": 5, "United Kingdom": 6, "Italy": 8,
    "Netherlands": 7, "Germany": 23,
}
TARGET_COUNTRIES = [
    COUNTRY_IDS["Belgium"],    # 2
    COUNTRY_IDS["Netherlands"],  # 7
    COUNTRY_IDS["Germany"],   # 23
]

LANGUAGE_IDS = {
    "English": 1, "French": 2, "German": 3,
    "Spanish": 4, "Italian": 5, "Japanese": 7,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://www.cardmarket.com/en/Pokemon",
}

SLEEP_SEC = 5  # base delay between requests (randomised +0-3s in practice)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _get(session, url: str, timeout: int = 20, retries: int = 3):
    """GET a URL; returns the Response or None on failure.
    Retries automatically on 429 / 503 with exponential backoff.
    """
    # curl_cffi sessions manage their own headers for TLS fingerprint integrity
    _is_cffi = type(session).__module__.startswith("curl_cffi")

    for attempt in range(1, retries + 1):
        try:
            if _is_cffi:
                resp = session.get(url, timeout=timeout)
            else:
                resp = session.get(url, headers=_HEADERS, timeout=timeout)

            if resp.status_code in (429, 503) and attempt < retries:
                wait = 10 * attempt
                print(f"  ! {resp.status_code} – waiting {wait}s before retry {attempt+1}/{retries}")
                time.sleep(wait)
                continue

            if resp.status_code not in (200,):
                print(f"  ! HTTP {resp.status_code} [{url[:80]}]")
                return None
            return resp
        except Exception as exc:
            if attempt < retries:
                time.sleep(8)
                continue
            print(f"  ! GET failed [{url[:80]}]: {exc}")
            return None
    return None


def parse_eur(text: str) -> float | None:
    """Extract a EUR float from strings like '54,99 €', '3.500,00 €', '54.99'."""
    if not text:
        return None
    cleaned = text.replace("\xa0", "").replace("€", "").replace("EUR", "").strip()
    match = re.search(r"([\d.,]+)", cleaned)
    if not match:
        return None
    raw = match.group(1)
    # European format: 1.234,56 → 1234.56
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _build_filtered_url(base_url: str, countries: list[int], language: int | None) -> str:
    """Append sellerCountry / language query params to a Cardmarket product URL.
    Uses comma-separated format: ?sellerCountry=2,7,23&language=1
    """
    params: list[str] = []
    if countries:
        params.append(f"sellerCountry={','.join(str(c) for c in countries)}")
    if language:
        params.append(f"language={language}")
    return f"{base_url}?{'&'.join(params)}"


# ---------------------------------------------------------------------------
# HTML parsers
# ---------------------------------------------------------------------------

def parse_price_guide(soup: BeautifulSoup) -> dict:
    """
    Extract the price-guide block from a Cardmarket product page.
    Returns keys: from_eur, price_trend_eur, avg_30d_eur,
                  avg_7d_eur, avg_1d_eur, available_items.
    """
    prices: dict = {
        "from_eur": None,
        "price_trend_eur": None,
        "avg_30d_eur": None,
        "avg_7d_eur": None,
        "avg_1d_eur": None,
        "available_items": None,
    }

    # Method 1: <dt> / <dd> pairs (Cardmarket's info-list)
    for dt in soup.find_all("dt"):
        label = dt.get_text(strip=True).lower()
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        val = dd.get_text(strip=True)

        if any(kw in label for kw in ("price trend", "trendpreis")):
            prices["price_trend_eur"] = parse_eur(val)
        elif any(kw in label for kw in ("30-day", "30 day", "30-tage")):
            prices["avg_30d_eur"] = parse_eur(val)
        elif any(kw in label for kw in ("7-day", "7 day", "7-tage")):
            prices["avg_7d_eur"] = parse_eur(val)
        elif any(kw in label for kw in ("1-day", "1 day", "1-tage")):
            prices["avg_1d_eur"] = parse_eur(val)
        elif label in ("from", "ab") or label.startswith("from ") or label.startswith("ab "):
            prices["from_eur"] = parse_eur(val)
        elif any(kw in label for kw in ("available", "verfügbar")):
            try:
                prices["available_items"] = int(re.sub(r"\D", "", val))
            except ValueError:
                pass

    # Method 2: regex fallback on plain text (handles DOM variations)
    text = soup.get_text(" ")
    if prices["price_trend_eur"] is None:
        m = re.search(r"Price Trend\s+([\d.,]+)\s*€", text)
        if m:
            prices["price_trend_eur"] = parse_eur(m.group(1))
    if prices["from_eur"] is None:
        m = re.search(r"\bFrom\b\s+([\d.,]+)\s*€", text)
        if m:
            prices["from_eur"] = parse_eur(m.group(1))
    if prices["avg_30d_eur"] is None:
        m = re.search(r"30[- ]day[s]? average\s+([\d.,]+)\s*€", text, re.IGNORECASE)
        if m:
            prices["avg_30d_eur"] = parse_eur(m.group(1))
    if prices["available_items"] is None:
        m = re.search(r"Available items\s+(\d+)", text, re.IGNORECASE)
        if m:
            prices["available_items"] = int(m.group(1))

    return prices


def download_image(image_url: str, product_id: str) -> str | None:
    """
    Download a Cardmarket product image and save it locally under data/images/.
    Returns the local file path (relative to project root) or None on failure.

    Cardmarket's S3 CDN requires Referer: https://www.cardmarket.com/ –
    browsers serving Streamlit send localhost as referer, causing 403.
    Downloading locally bypasses this completely.
    """
    import requests as _req
    ext = ".jpg" if ".jpg" in image_url.lower() else ".png"
    dest = IMAGES_DIR / f"{product_id}{ext}"
    try:
        r = _req.get(
            image_url,
            headers={
                "Referer": "https://www.cardmarket.com/",
                "User-Agent": _HEADERS["User-Agent"],
            },
            timeout=15,
        )
        if r.status_code == 200 and r.content:
            dest.write_bytes(r.content)
            # Return POSIX-style path relative to project root (forward slashes,
            # works on both Windows and Linux / Streamlit Cloud)
            return dest.relative_to(DATA_DIR.parent).as_posix()
        print(f"  ! image download {r.status_code}: {image_url[:80]}")
    except Exception as exc:
        print(f"  ! image download failed: {exc}")
    return None


def parse_product_image(soup: BeautifulSoup) -> str | None:
    """Return the main product image URL from a Cardmarket product page.

    Cardmarket lazy-loads images, so the URL may be in src, data-src,
    data-lazy-src, or srcset – or embedded in raw JS / JSON-LD.
    """
    S3_HOST = "product-images.s3.cardmarket.com"

    # 1. Walk every <img> and check all common src-like attributes
    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy", "data-lazy-src",
                     "data-original", "data-echo"):
            val = img.get(attr, "")
            if S3_HOST in val:
                return val.split(" ")[0]  # strip srcset descriptors if any

    # 2. og:image meta tag
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"]

    # 3. Scan raw HTML for the S3 URL pattern
    raw = str(soup)
    m = re.search(r'https?://product-images\.s3\.cardmarket\.com/[^\s"\']+'  , raw)
    if m:
        return m.group(0)

    # 4. JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(script.string or "{}")
            for key in ("image", "thumbnail", "thumbnailUrl"):
                val = ld.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    return val
                if isinstance(val, list) and val:
                    return val[0]
        except Exception:
            pass

    return None


def parse_product_name(soup: BeautifulSoup) -> str | None:
    """Return the product name from the <h1> of a product page."""
    h1 = soup.find("h1")
    if h1:
        lines = [ln.strip() for ln in h1.get_text(separator="\n").splitlines() if ln.strip()]
        if lines:
            return lines[0]
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_cardmarket(session, query: str) -> list[dict]:
    """
    Search Cardmarket for Pokemon products matching query.

    Returns list of dicts: {name, url, from_eur, image_url}
    """
    search_url = f"{BASE_URL}/Products/Search?searchString={quote_plus(query)}"
    resp = _get(session, search_url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[dict] = []
    seen: set[str] = set()

    # Category-index pages to skip (they are not individual product pages)
    _CATEGORY_SLUGS = {
        "Singles", "Boosters", "Booster-Boxes", "Elite-Trainer-Boxes",
        "Special-Products", "Sealed-Products", "Accessories", "Storage",
        "Sets-Lots-Collections", "Cardmarket", "Search",
    }

    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if "/en/Pokemon/Products/" not in href:
            continue
        parts = [p for p in href.split("/") if p]
        if len(parts) < 5:
            continue
        if parts[-1] in _CATEGORY_SLUGS:
            continue

        full_url = (
            f"https://www.cardmarket.com{href}" if href.startswith("/") else href
        ).split("?")[0]

        if full_url in seen:
            continue
        seen.add(full_url)

        # Parse name and "From" price from link text
        # Cardmarket text pattern: "Product Name  Expansion  Product Name From 299,00 €"
        raw_text = a.get_text(" ", strip=True)
        if "From" in raw_text:
            name_part, price_part = raw_text.split("From", 1)
            from_eur = parse_eur(price_part)
        else:
            name_part = raw_text
            from_eur = None

        # Remove duplicated name (Cardmarket repeats it after the expansion)
        name_part = name_part.strip()
        words = name_part.split()
        half = len(words) // 2
        if half > 2 and words[:half] == words[half:]:
            name_part = " ".join(words[:half])
        name = name_part[:120].strip()
        if not name or len(name) < 5:
            continue

        img_tag = a.find("img")
        image_url = img_tag["src"] if img_tag and img_tag.get("src") else None

        results.append({"name": name, "url": full_url, "from_eur": from_eur, "image_url": image_url})
        if len(results) >= 12:
            break

    return results


def fetch_product_data(
    session,
    url: str,
    countries: list[int] | None = None,
    language: int | None = None,
) -> dict:
    """
    Fetch product details from a Cardmarket product page.

    Returns dict with:
      name, image_url, cardmarket_url, scraped_at,
      prices          – global price guide,
      prices_filtered – price guide with BE/DE/NL + English filter applied
    """
    resp = _get(session, url)
    if not resp:
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    result = {
        "name":           parse_product_name(soup),
        "image_url":      parse_product_image(soup),
        "cardmarket_url": url,
        "scraped_at":     datetime.now(timezone.utc).isoformat(),
        "prices":         parse_price_guide(soup),
        "prices_filtered": {},
    }

    if countries:
        filtered_url = _build_filtered_url(url, countries, language)
        time.sleep(SLEEP_SEC)
        filtered_resp = _get(session, filtered_url)
        if filtered_resp:
            result["prices_filtered"] = parse_price_guide(
                BeautifulSoup(filtered_resp.text, "html.parser")
            )

    return result



# Map language name → flag emoji
_LANGUAGE_FLAG = {
    "English": "🇬🇧", "French": "🇫🇷", "German": "🇩🇪",
    "Spanish": "🇪🇸", "Italian": "🇮🇹", "Japanese": "🇯🇵",
    "Portuguese": "🇵🇹", "Korean": "🇰🇷",
}

# Map country name → flag emoji
_COUNTRY_FLAG = {
    "Germany": "🇩🇪", "Netherlands": "🇳🇱", "Belgium": "🇧🇪",
    "France": "🇫🇷", "United Kingdom": "🇬🇧", "Austria": "🇦🇹",
    "Italy": "🇮🇹", "Spain": "🇪🇸",
}


def _has_cls(el, name: str) -> bool:
    """Return True if a BeautifulSoup element has the given CSS class."""
    c = el.get("class", [])
    joined = c if isinstance(c, str) else " ".join(c)
    return name in joined


def parse_offers(soup: BeautifulSoup, max_offers: int = 10) -> list[dict]:
    """
    Extract the top N cheapest offer rows from a Cardmarket product page.

    Returns list of dicts:
      seller, seller_info, item_location, item_location_flag,
      language, language_flag, condition, price_eur, quantity.
    """
    offers: list[dict] = []

    rows = soup.find_all(
        "div",
        class_=lambda c: c and "article-row" in (c if isinstance(c, str) else " ".join(c)),
    )

    for row in rows:
        offer: dict = {"quantity": 1}

        # ── Seller name ──────────────────────────────────────────────────
        seller_a = row.find("a", href=lambda h: h and "/Users/" in (h or ""))
        if not seller_a:
            continue
        offer["seller"] = seller_a.get_text(strip=True)

        # ── Seller info: "160 Sales | 5 Available items" ─────────────────
        # Stored as title/data-bs-original-title on the badge span
        for span in row.find_all("span"):
            if _has_cls(span, "sell-count"):
                raw = (span.get("title") or span.get("data-bs-original-title") or "")
                # Replace non-breaking spaces with regular spaces
                offer["seller_info"] = raw.replace("\xa0", " ").strip()
                break

        # ── Item location: "Germany" / "Netherlands" / "Belgium" ─────────
        # Stored as title="Item location: X" on the country icon span
        loc_country = ""
        for span in row.find_all(["span", "div"]):
            for attr in ("title", "data-bs-original-title", "data-original-title"):
                t = span.get(attr, "")
                if t.startswith("Item location:"):
                    loc_country = t.replace("Item location:", "").strip()
                    break
            if loc_country:
                break
        offer["item_location"] = loc_country
        offer["item_location_flag"] = _COUNTRY_FLAG.get(loc_country, "")

        # ── Language: "English" etc. ──────────────────────────────────────
        # Stored as data-original-title on the flag sprite span in product-attributes
        lang = ""
        LANGS = {"English", "French", "German", "Spanish", "Italian", "Japanese"}
        attrs_div = None
        for div in row.find_all("div"):
            if _has_cls(div, "product-attributes"):
                attrs_div = div
                break
        if attrs_div:
            for span in attrs_div.find_all("span"):
                for attr in ("data-original-title", "title"):
                    t = span.get(attr, "")
                    if t in LANGS:
                        lang = t
                        break
                if lang:
                    break
        offer["language"] = lang
        offer["language_flag"] = _LANGUAGE_FLAG.get(lang, "")

        # ── Condition / comment ───────────────────────────────────────────
        # Stored in .product-comments > .text-truncate span
        condition = ""
        for div in row.find_all("div"):
            if _has_cls(div, "product-comments"):
                # prefer the truncated text span (desktop view)
                for span in div.find_all("span"):
                    if _has_cls(span, "text-truncate"):
                        condition = span.get_text(strip=True)
                        break
                if not condition:
                    condition = div.get_text(strip=True)
                break
        offer["condition"] = condition[:120]

        # ── Price ─────────────────────────────────────────────────────────
        # Desktop: .price-container .color-primary  Mobile: .mobile-offer-container .color-primary
        price_val: float | None = None
        for div in row.find_all("div"):
            if _has_cls(div, "price-container"):
                for span in div.find_all("span"):
                    if _has_cls(span, "color-primary"):
                        txt = span.get_text(strip=True)
                        if "€" in txt:
                            price_val = parse_eur(txt)
                            break
                if price_val:
                    break
        # Fallback: any .color-primary span with €
        if price_val is None:
            for span in row.find_all("span"):
                if _has_cls(span, "color-primary"):
                    txt = span.get_text(strip=True)
                    if "€" in txt:
                        price_val = parse_eur(txt)
                        if price_val:
                            break

        if price_val is None:
            continue
        offer["price_eur"] = price_val

        # ── Quantity ──────────────────────────────────────────────────────
        for span in row.find_all("span"):
            if _has_cls(span, "item-count"):
                try:
                    offer["quantity"] = int(re.sub(r"\D", "", span.get_text()) or "1")
                except ValueError:
                    pass
                break

        offers.append(offer)

    offers.sort(key=lambda o: o.get("price_eur", 999_999))
    return offers[:max_offers]


def fetch_offers_for_product(session, url: str, max_offers: int = 10) -> list[dict]:
    """
    Fetch the top N offers from a filtered Cardmarket product URL.
    The URL should already include the sellerCountry/language query params.
    Raises RuntimeError on HTTP failure so callers can surface the error.
    """
    resp = _get(session, url, retries=2)  # one retry with backoff before giving up
    if not resp:
        raise RuntimeError(
            "Cardmarket rate-limited this request (429). "
            "Wait 30–60 seconds then click \u21bb Refresh."
        )
    soup = BeautifulSoup(resp.text, "html.parser")
    return parse_offers(soup, max_offers=max_offers)


def update_all_products(
    countries: list[int] | None = None,
    language: int | None = None,
    skip_if_fresh_hours: float = 6,
    session=None,
) -> int:
    """
    Refresh prices for every product in products.json.
    Skips products whose last_scraped is within skip_if_fresh_hours (default 6h)
    to avoid hammering Cardmarket and hitting rate limits.
    Saves updated products.json and appends to price_history.csv.
    Returns the number of successfully updated products.
    """
    import random
    with open(PRODUCTS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    if session is None:
        session = create_session()
    history_rows: list[dict] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    now_utc = datetime.now(timezone.utc)
    updated = 0
    skipped_fresh = 0

    all_products = data.get("historical_comps", []) + data.get("watchlist", [])

    for product in all_products:
        url = product.get("cardmarket_url")
        if not url:
            continue

        # Skip if recently scraped
        last = product.get("last_scraped")
        if last and skip_if_fresh_hours > 0:
            try:
                last_dt = datetime.fromisoformat(last)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                age_h = (now_utc - last_dt).total_seconds() / 3600
                if age_h < skip_if_fresh_hours:
                    skipped_fresh += 1
                    print(f"  ↷ skipping (fresh {age_h:.1f}h ago): {product['name']}")
                    continue
            except ValueError:
                pass

        print(f"Fetching: {product['name']}")
        info = fetch_product_data(session, url, countries, language)
        if not info:
            print("  ! skipped (fetch failed)")
            time.sleep(SLEEP_SEC + random.uniform(0, 3))
            continue

        p  = info.get("prices", {})
        pf = info.get("prices_filtered", {})

        if p.get("price_trend_eur") is not None:
            product["current_price_eur"] = p["price_trend_eur"]
        if p.get("from_eur") is not None:
            product["price_from_eur"] = p["from_eur"]
        if p.get("avg_30d_eur") is not None:
            product["avg_30d_eur"] = p["avg_30d_eur"]
        if p.get("avg_7d_eur") is not None:
            product["avg_7d_eur"] = p["avg_7d_eur"]
        if info.get("image_url"):          # always refresh – not just when missing
            remote_url = info["image_url"]
            pid = product.get("id", "unknown")
            # Download locally so Streamlit can display without hotlink issues
            local_path = download_image(remote_url, pid)
            product["image_url"] = local_path if local_path else remote_url
        if pf.get("from_eur") is not None:
            product["price_from_filtered_eur"] = pf["from_eur"]
        if pf.get("available_items") is not None:
            product["available_filtered"] = pf["available_items"]
        product["last_scraped"] = timestamp

        # Fetch and cache top 10 listings (BE/NL/DE · English) so the
        # Streamlit Cloud deployment can display them without live requests.
        if countries and language:
            try:
                filtered_url = _build_filtered_url(url, countries, language)
                offers = fetch_offers_for_product(session, filtered_url, max_offers=10)
                if offers:
                    product["listings"] = offers
                    product["listings_scraped_at"] = timestamp
                    print(f"  → cached {len(offers)} listings")
            except Exception as exc:
                print(f"  ! listings fetch failed: {exc}")
            time.sleep(SLEEP_SEC + random.uniform(0, 2))

        history_rows.append({
            "timestamp":          timestamp,
            "product_id":         product.get("id", ""),
            "price_trend_eur":    p.get("price_trend_eur"),
            "from_eur":           p.get("from_eur"),
            "avg_30d_eur":        p.get("avg_30d_eur"),
            "avg_7d_eur":         p.get("avg_7d_eur"),
            "avg_1d_eur":         p.get("avg_1d_eur"),
            "from_filtered_eur":  pf.get("from_eur"),
            "available_filtered": pf.get("available_items"),
        })
        updated += 1

        print(
            f"  trend: €{p.get('price_trend_eur', '–')} | "
            f"from: €{p.get('from_eur', '–')} | "
            f"BE/DE/NL from: €{pf.get('from_eur', '–')}"
        )
        time.sleep(SLEEP_SEC + random.uniform(0, 4))

    with open(PRODUCTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if history_rows:
        fieldnames = [
            "timestamp", "product_id", "price_trend_eur", "from_eur",
            "avg_30d_eur", "avg_7d_eur", "avg_1d_eur",
            "from_filtered_eur", "available_filtered",
        ]
        write_header = not HISTORY_PATH.exists()
        with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerows(history_rows)

    print(f"\nDone. Updated {updated}/{len(all_products)} products (skipped {skipped_fresh} fresh). History -> {HISTORY_PATH}")
    return updated


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cardmarket scraper – Pokemon Investment Tracker"
    )
    parser.add_argument("--search", metavar="QUERY", help="Search Cardmarket by product name")
    parser.add_argument("--url",    metavar="URL",   help="Fetch details for a specific URL")
    parser.add_argument(
        "--no-filter", action="store_true",
        help="Skip BE/DE/NL seller-country and English language filtering",
    )
    args = parser.parse_args()

    countries = None if args.no_filter else TARGET_COUNTRIES
    language  = None if args.no_filter else LANGUAGE_IDS["English"]
    session   = create_session()

    if args.search:
        print(f"Searching: {args.search!r}")
        results = search_cardmarket(session, args.search)
        if not results:
            print("No results found.")
        for i, r in enumerate(results, 1):
            price = f"  From €{r['from_eur']:.2f}" if r.get("from_eur") else ""
            print(f"  {i:2d}. {r['name']}{price}\n      {r['url']}")
        return

    if args.url:
        print(f"Fetching: {args.url}")
        info = fetch_product_data(session, args.url, countries, language)
        print(json.dumps(info, indent=2, default=str))
        return

    update_all_products(countries, language)


if __name__ == "__main__":
    main()
