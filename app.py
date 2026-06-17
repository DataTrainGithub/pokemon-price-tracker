"""
app.py  –  Pokémon Sealed Product Price Tracker
Prices sourced from Cardmarket | BE · NL · DE sellers | English sealed only
RUN:  streamlit run app.py
"""
import base64
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

DATA_PATH    = Path(__file__).parent / "data" / "products.json"
HISTORY_PATH = Path(__file__).parent / "data" / "price_history.csv"
IMAGES_DIR   = Path(__file__).parent / "data" / "images"

_CM_FILTER = "?sellerCountry=2,7,23&language=1"


_APP_DIR = Path(__file__).parent


def _image_to_data_uri(path_or_url: str) -> str:
    """Convert a local image file to a base64 data URI for Streamlit ImageColumn.
    Handles both POSIX and Windows-style relative paths stored in products.json.
    If it's a remote URL or the file doesn't exist, return the value as-is.
    """
    # Normalise backslashes so Windows-saved paths work on Linux (Streamlit Cloud)
    normalised = path_or_url.replace("\\", "/")
    # Resolve relative to the app directory
    p = (_APP_DIR / normalised).resolve()
    if p.exists():
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"
    return path_or_url  # remote URL fallback

# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Pokémon Sealed Tracker",
    page_icon="PT",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Pastel / minimalist theme ───────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], section.main {
    background-color: #f7f8fc !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px;
    color: #1e2130;
}

/* hide default streamlit header chrome */
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none; }

/* ── Typography ── */
h1 {
    font-size: 1.35rem !important;
    font-weight: 600 !important;
    color: #1e2130 !important;
    margin-bottom: 0.15rem !important;
    letter-spacing: -0.01em;
}
h2 { font-size: 1.05rem !important; font-weight: 600 !important; color: #2c3354 !important; }
h3 { font-size: 0.95rem !important; font-weight: 600 !important; color: #2c3354 !important; }
h4 { font-size: 0.85rem !important; font-weight: 600 !important; color: #2c3354 !important;
     margin: 0.5rem 0 0.25rem !important; }

p, li, label, caption { color: #4b5275; }

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: #ffffff;
    border: 1px solid #e4e8f4;
    border-radius: 10px;
    padding: 0.6rem 0.8rem !important;
    box-shadow: 0 1px 3px rgba(60,70,110,0.05);
}
[data-testid="stMetricValue"] {
    font-size: 1.0rem !important;
    font-weight: 600 !important;
    color: #1e2130 !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.68rem !important;
    font-weight: 500 !important;
    color: #7c87a8 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
[data-testid="stMetricDelta"] { font-size: 0.72rem !important; }

/* ── Tabs ── */
[data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 2px solid #e4e8f4 !important;
    gap: 0 !important;
}
button[data-baseweb="tab"] {
    background: transparent !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    color: #7c87a8 !important;
    padding: 0.5rem 1.1rem !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    margin-bottom: -2px;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #4f5fc4 !important;
    border-bottom: 2px solid #4f5fc4 !important;
    font-weight: 600 !important;
}
button[data-baseweb="tab"]:hover { color: #4f5fc4 !important; background: #f0f2fb !important; }

/* ── Buttons (all variants, force light regardless of prefers-color-scheme) ── */
.stButton > button,
.stButton > button:link,
.stButton > button:visited,
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-primary"] {
    background: #ffffff !important;
    border: 1px solid #d4d8ef !important;
    color: #4b5275 !important;
    border-radius: 7px !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    padding: 0.3rem 0.75rem !important;
    box-shadow: none !important;
    transition: background 0.15s, border-color 0.15s;
}
.stButton > button:hover,
.stButton > button:focus,
[data-testid="stBaseButton-secondary"]:hover,
[data-testid="stBaseButton-primary"]:hover {
    background: #f0f2fb !important;
    border-color: #a3a9d4 !important;
    color: #2c3354 !important;
    box-shadow: none !important;
}

/* ── Inputs / selects ── */
[data-baseweb="select"], [data-baseweb="input"] {
    background: #ffffff !important;
    border-color: #d4d8ef !important;
    border-radius: 7px !important;
    font-size: 0.8rem !important;
}
[data-baseweb="select"] > div { background: #ffffff !important; }

/* ── Dataframe / table ── */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
[data-testid="stDataFrameGlideDataEditor"] { font-size: 0.78rem !important; }

/* ── Divider ── */
hr { border-color: #e4e8f4 !important; margin: 1rem 0 !important; }

/* ── Alerts / info boxes ── */
[data-testid="stInfo"]    { background: #eef1fb !important; border-left-color: #7b8cde !important; }
[data-testid="stWarning"] { background: #fef8ee !important; border-left-color: #e8b84b !important; }
[data-testid="stSuccess"] { background: #edf7f2 !important; border-left-color: #5a9e78 !important; }
[data-testid="stError"]   { background: #fdf0f0 !important; border-left-color: #c97474 !important; }

/* ── Country source badge ── */
.src-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: #eef1fb;
    color: #4f5fc4;
    border: 1px solid #d4daff;
    border-radius: 5px;
    padding: 3px 10px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}

/* ── Offers table ── */
.ot { border-collapse: collapse; width: 100%; border-radius: 8px; overflow: hidden; }
.ot th {
    background: #f0f2fb;
    color: #4b5275;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 7px 12px;
    text-align: left;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid #e4e8f4;
}
.ot td {
    font-size: 0.78rem;
    padding: 6px 12px;
    border-bottom: 1px solid #f0f2f8;
    color: #2c3354;
    background: #ffffff;
}
.ot tr:hover td { background: #f7f8fd; }

/* ── Product cards (ROI visual grid) ── */
.pc-card {
    background: #ffffff;
    border: 1px solid #e4e8f4;
    border-radius: 10px;
    padding: 0.65rem 0.75rem;
    margin-bottom: 0.5rem;
    box-shadow: 0 1px 3px rgba(60,70,110,0.04);
}
.pc-name  { font-size: 0.76rem; font-weight: 600; color: #1e2130; line-height: 1.35; margin-bottom: 3px; }
.pc-price { font-size: 0.72rem; color: #7c87a8; margin-bottom: 2px; }
.pc-pos   { font-size: 0.8rem; font-weight: 700; color: #2d7d52; }
.pc-neg   { font-size: 0.8rem; font-weight: 700; color: #b85450; }
.pc-neu   { font-size: 0.8rem; color: #9ca3af; }
.pc-link  { font-size: 0.7rem; color: #4f5fc4; text-decoration: none; }

/* ── Hide dataframe row-selection checkbox column ── */
[data-testid="stDataFrame"] [role="rowheader"],
[data-testid="stDataFrame"] [role="columnheader"]:first-of-type:has(input[type="checkbox"]) {
    display: none !important;
    width: 0 !important;
    min-width: 0 !important;
    padding: 0 !important;
}
/* Make the whole row feel clickable */
[data-testid="stDataFrame"] [role="row"] { cursor: pointer !important; }

/* ── Spinner ── */
[data-testid="stSpinner"] > div { border-top-color: #4f5fc4 !important; }

/* ── Full-screen refresh overlay ── */
.refresh-overlay {
    position: fixed;
    inset: 0;
    z-index: 99999;
    background: rgba(247, 248, 252, 0.88);
    backdrop-filter: blur(4px);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1.4rem;
}
.refresh-overlay .ro-ring {
    width: 64px; height: 64px;
    border: 5px solid #e4e8f4;
    border-top-color: #4f5fc4;
    border-radius: 50%;
    animation: ro-spin 0.8s linear infinite;
}
.refresh-overlay .ro-label {
    font-size: 1rem;
    font-weight: 600;
    color: #2c3354;
    letter-spacing: -0.01em;
}
.refresh-overlay .ro-sub {
    font-size: 0.78rem;
    color: #7c87a8;
    margin-top: -0.8rem;
}
@keyframes ro-spin { to { transform: rotate(360deg); } }

/* ── Caption ── */
.stCaption { color: #9ca3af !important; font-size: 0.68rem !important; }

/* ── Dataframe: force light theme regardless of system ── */
[data-testid="stDataFrame"] > div,
[data-testid="stDataFrameResizable"],
.glideDataEditor,
.dvMainCanvasBg { background: #ffffff !important; }

/* Dataframe header and cell text */
.gdg-header-row     { background: #f0f2fb !important; color: #4b5275 !important; }
.gdg-cell           { color: #1e2130 !important; background: #ffffff !important; }
.gdg-cell:hover     { background: #f7f8fd !important; }

/* Glide-data-grid canvas (Streamlit uses this internally) – set via CSS vars */
[data-testid="stDataFrame"] { --gdg-bg-cell: #ffffff; --gdg-bg-header: #f0f2fb;
    --gdg-text-dark: #1e2130; --gdg-text-medium: #4b5275; }

/* Multiselect tags */
[data-baseweb="tag"] {
    background: #eef1fb !important;
    color: #4f5fc4 !important;
    border: 1px solid #d4daff !important;
}
[data-baseweb="tag"] span { color: #4f5fc4 !important; }
[data-baseweb="tag"] button svg { fill: #4f5fc4 !important; }

/* Select / multiselect dropdown menu */
[data-baseweb="menu"], [role="listbox"] {
    background: #ffffff !important;
    border: 1px solid #e4e8f4 !important;
    border-radius: 8px !important;
}
[role="option"] { color: #2c3354 !important; background: #ffffff !important; }
[role="option"]:hover, [aria-selected="true"][role="option"] {
    background: #f0f2fb !important; color: #4f5fc4 !important;
}

/* Checkbox */
[data-testid="stCheckbox"] span[data-testid="stWidgetLabel"] { color: #4b5275 !important; }

/* Expander */
[data-testid="stExpander"] details {
    background: #ffffff !important;
    border: 1px solid #e4e8f4 !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary {
    color: #2c3354 !important;
    font-weight: 600 !important;
    font-size: 0.84rem !important;
    background: #f7f8fc !important;
    border-radius: 10px !important;
    padding: 0.5rem 0.75rem !important;
}
[data-testid="stExpander"] summary:hover { background: #f0f2fb !important; }
[data-testid="stExpander"] > details > div {
    background: #ffffff !important;
    border-top: 1px solid #e4e8f4 !important;
    padding: 1rem 0.75rem !important;
}

/* Tooltip/popover */
[data-testid="stTooltipContent"], [data-testid="stTooltipHoverTarget"] + div {
    background: #ffffff !important;
    border: 1px solid #e4e8f4 !important;
    color: #2c3354 !important;
    border-radius: 7px !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json() -> dict:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=300)
def get_all_products() -> list[dict]:
    data  = _load_json()
    today = date.today()
    out: list[dict] = []
    for src, is_hist in [("historical_comps", True), ("watchlist", False)]:
        for raw in data.get(src, []):
            p = dict(raw)
            p["_is_historical"] = is_hist

            oop_raw = p.get("oop_date")
            if oop_raw:
                try:
                    oop_dt = date.fromisoformat(str(oop_raw)[:10])
                    p["_is_oop"]      = oop_dt <= today
                    p["_oop_display"] = str(oop_raw)[:7]
                except ValueError:
                    p["_is_oop"]      = False
                    p["_oop_display"] = str(oop_raw)
            else:
                m = p.get("months_to_oop")
                p["_is_oop"]      = (m == 0)
                p["_oop_display"] = f"~{m} mo" if m else "?"

            p["_from"] = (
                p.get("price_from_filtered_eur")
                or p.get("price_from_eur")
            )
            # _roi uses _from; fall back to trend only for ROI estimate if no from-price yet
            msrp = p.get("msrp_eur")
            frm  = p.get("_from") or p.get("current_price_eur")
            p["_roi"] = round((frm - msrp) / msrp * 100, 1) if (msrp and frm and msrp > 0) else None

            out.append(p)
    return out


def refresh() -> None:
    get_all_products.clear()
    st.rerun()


def _price_data_age_hours() -> float | None:
    """Return hours since the most recent last_scraped timestamp across all products."""
    try:
        data = _load_json()
        timestamps = [
            p.get("last_scraped")
            for section in ("historical_comps", "watchlist")
            for p in data.get(section, [])
            if p.get("last_scraped")
        ]
        if not timestamps:
            return None
        latest = max(timestamps)
        dt = datetime.fromisoformat(latest)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return None


def feur(v) -> str:
    if v is None:
        return "—"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"€ {s}"


def froi(v) -> str:
    if v is None:
        return "—"
    return f"+{v:.0f} %" if v >= 0 else f"{v:.0f} %"


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
hc1, hc2, hc3 = st.columns([5, 1, 1])
with hc1:
    st.title("Pokémon Sealed Product Price Tracker")
    st.markdown(
        '<span class="src-badge">BE · NL · DE &nbsp; | &nbsp; English sealed only</span>',
        unsafe_allow_html=True,
    )
with hc2:
    if st.button("Refresh Prices", use_container_width=True,
                 help="Fetch latest prices from Cardmarket for all products"):
        _overlay = st.empty()
        _overlay.markdown(
            '<div class="refresh-overlay">'
            '<div class="ro-ring"></div>'
            '<div class="ro-label">Refreshing prices…</div>'
            '<div class="ro-sub">Fetching from Cardmarket &mdash; this can take a few minutes</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        try:
            from scraper.cardmarket_scraper import update_all_products
            n = update_all_products(countries=[2, 7, 23], language=1)
            _overlay.empty()
            refresh()
            st.success(f"Updated {n} products")
        except Exception as exc:
            _overlay.empty()
            st.error(str(exc))
with hc3:
    if st.button("Clear cache", use_container_width=True):
        refresh()

# ── Staleness warning ────────────────────────────────────────────────────────
_age_h = _price_data_age_hours()
if _age_h is not None and _age_h > 24:
    _age_label = f"{int(_age_h)}h" if _age_h < 48 else f"{int(_age_h / 24)}d"
    st.warning(
        f"Price data is **{_age_label} old**. "
        "Click **Refresh Prices** to fetch the latest from Cardmarket."
    )

st.write("")
all_products = get_all_products()

# ---------------------------------------------------------------------------
# TABS
# ---------------------------------------------------------------------------
tab_all, tab_roi, tab_hist = st.tabs([
    "All Products",
    "Historical ROI",
    "Price History",
])

# ==========================================================================
# TAB 1 – ALL PRODUCTS
# ==========================================================================
with tab_all:
    fc1, fc2, fc3, fc4 = st.columns([3, 2, 2, 1])

    _all_names = [p["name"] for p in all_products]
    with fc1:
        srch = st.selectbox(
            "srch",
            options=[""] + _all_names,
            index=0,
            format_func=lambda x: "All Products" if x == "" else x,
            label_visibility="collapsed",
            key="all_search",
        )
    _types = sorted({p.get("type", "Other") for p in all_products})
    with fc2:
        sel_types = st.multiselect(
            "t", _types, default=_types,
            label_visibility="collapsed",
            placeholder="Filter by type…",
        )
    with fc3:
        sort_col = st.selectbox(
            "s",
            ["Name", "From Price", "MSRP", "ROI %", "Release Date"],
            label_visibility="collapsed",
        )
    with fc4:
        show_oop = st.checkbox("OOP only", value=False)

    filt = [
        p for p in all_products
        if (not srch or p["name"] == srch)
        and (not sel_types or p.get("type", "Other") in sel_types)
        and (not show_oop or p.get("_is_oop"))
    ]

    _sm = {
        "Name":         ("name",         False),
        "From Price":   ("_from",        True),
        "MSRP":         ("msrp_eur",     True),
        "ROI %":        ("_roi",         True),
        "Release Date": ("release_date", True),
    }
    sk, rev = _sm.get(sort_col, ("name", False))
    filt = sorted(
        filt,
        key=lambda p: (
            p.get(sk) is None,
            p.get(sk) or "" if sk in ("name", "release_date") else (p.get(sk) or 0),
        ),
        reverse=rev,
    )

    st.caption(f"{len(filt)} of {len(all_products)} products  ·  click a row to view details")

    rows = [{
        "":              _image_to_data_uri(p["image_url"]) if p.get("image_url") else "",
        "Product":       p.get("name", ""),
        "Type":          p.get("type", "—"),
        "MSRP":          p.get("msrp_eur"),
        "From (BE·NL·DE)": p.get("_from"),
        "ROI %":         p.get("_roi"),
        "Released":      (p.get("release_date") or "")[:7],
        "Est. OOP":      p.get("_oop_display", "?"),
        "View":          (p.get("cardmarket_url", "") + _CM_FILTER) if p.get("cardmarket_url") else "",
    } for p in filt]

    # Auto-size for small tables (no empty padding rows); scrollable for large ones
    _tbl_height = ("content" if len(rows) <= 6 else min(40 + len(rows) * 44, 460)) if rows else 80

    sel_state = st.dataframe(
        pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Product"]),
        use_container_width=True, hide_index=True, height=_tbl_height,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "":              st.column_config.ImageColumn("", width="small"),
            "Product":       st.column_config.TextColumn("Product", width="large"),
            "Type":          st.column_config.TextColumn("Type", width="small"),
            "MSRP":          st.column_config.NumberColumn("MSRP", format="€%.2f", width="small"),
            "From (BE·NL·DE)": st.column_config.NumberColumn("From (BE·NL·DE)", format="€%.2f", width="medium"),
            "ROI %":         st.column_config.NumberColumn("ROI %", format="%.0f%%", width="small"),
            "Released":      st.column_config.TextColumn("Released", width="small"),
            "Est. OOP":      st.column_config.TextColumn("Est. OOP", width="small"),
            "View":          st.column_config.LinkColumn("Cardmarket", display_text="View", width="small"),
        },
    )

    # Persist selection in session_state so detail survives filter changes
    _sel_rows = (sel_state.selection.rows if sel_state and sel_state.selection else [])
    if _sel_rows and _sel_rows[0] < len(filt):
        st.session_state["_selected_product_id"] = filt[_sel_rows[0]].get("id", "")

    # Resolve product to show detail for
    _sel_id = st.session_state.get("_selected_product_id")
    if _sel_id:
        det = next((p for p in filt if p.get("id") == _sel_id), None)
        # If the selection is no longer in the filtered list, fall back to single-result auto-open
        if det is None and len(filt) == 1:
            det = filt[0]
    elif len(filt) == 1:
        det = filt[0]
    else:
        det = None

    if det:
        st.write("")
        with st.expander(f"Detail — {det['name']}", expanded=True):
            cm_base = det.get("cardmarket_url", "")
            cm_filt = f"{cm_base}{_CM_FILTER}" if cm_base else ""

            d_left, d_right = st.columns([1, 3], gap="large")

            with d_left:
                img = det.get("image_url")
                if img:
                    try:
                        img_src = _image_to_data_uri(img)
                        st.image(img_src, use_container_width=True)
                    except Exception:
                        st.caption("Image unavailable")
                else:
                    st.caption("No image yet — run Refresh Prices")

                st.write("")
                if cm_filt:
                    st.markdown(
                        f'<a href="{cm_filt}" target="_blank" '
                        f'style="font-size:0.78rem;color:#4f5fc4;text-decoration:none;'
                        f'border:1px solid #d4daff;border-radius:6px;padding:4px 10px;">'
                        f'View on Cardmarket</a>',
                        unsafe_allow_html=True,
                    )
                st.write("")
                st.markdown(
                    '<span class="src-badge">BE · NL · DE &nbsp;|&nbsp; English</span>',
                    unsafe_allow_html=True,
                )

            with d_right:
                parts = []
                if det.get("type"):
                    parts.append(det["type"])
                rs = (det.get("reprint_status") or "").replace("_", " ").title()
                if rs:
                    parts.append(rs)
                for tg in (det.get("tags") or [])[:3]:
                    parts.append(tg.replace("_", " ").title())
                if parts:
                    st.caption("  ·  ".join(parts))

                st.write("")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("From (BE·NL·DE)", feur(det.get("price_from_filtered_eur")),
                          help="Lowest listing: Belgium / Netherlands / Germany – English sealed only")
                m2.metric("From (Global)", feur(det.get("price_from_eur")))
                m3.metric("Price Trend", feur(det.get("current_price_eur")))
                m4.metric("ROI vs MSRP", froi(det.get("_roi")))

                st.write("")
                m5, m6, m7, m8 = st.columns(4)
                m5.metric("MSRP",        feur(det.get("msrp_eur")))
                m6.metric("30d Average", feur(det.get("avg_30d_eur")))
                m7.metric("7d Average",  feur(det.get("avg_7d_eur")))
                m8.metric("Released",    (det.get("release_date") or "—")[:7])

                st.write("")
                st.write("")
                mn1, mn2, _, _ = st.columns(4)
                mn1.metric("Est. OOP", det.get("_oop_display", "—"))

                st.write("")
                caps = []
                avail = det.get("available_filtered")
                if avail:
                    caps.append(f"{avail} listings (BE/NL/DE · English)")
                lsc = det.get("last_scraped")
                if lsc:
                    caps.append(f"Prices updated: {str(lsc)[:10]}")
                if caps:
                    st.caption("  ·  ".join(caps))

            st.divider()

            if not cm_filt:
                st.warning("No Cardmarket URL configured for this product.")
            else:
                offers_key = f"_offers_{det.get('id', '')}"
                offers_ts_key = f"_offers_ts_{det.get('id', '')}"

                # Auto-fetch on first open; show refresh button for subsequent reloads
                if offers_key not in st.session_state:
                    with st.spinner("Loading listings…"):
                        try:
                            from scraper.cardmarket_scraper import (
                                create_session, fetch_offers_for_product,
                            )
                            sess = create_session()
                            off = fetch_offers_for_product(sess, cm_filt, max_offers=10)
                            st.session_state[offers_key] = off
                            st.session_state[offers_ts_key] = datetime.now(timezone.utc)
                        except Exception as exc:
                            st.error(f"Could not load listings: {exc}")
                            st.session_state[offers_key] = []

                # Header row: title + refresh button + timestamp
                _lh1, _lh2 = st.columns([4, 1])
                with _lh1:
                    st.markdown("**Current Listings** &nbsp;—&nbsp; Belgium · Netherlands · Germany · English sealed")
                    _ts = st.session_state.get(offers_ts_key)
                    if _ts:
                        st.caption(f"Fetched at {_ts.strftime('%H:%M:%S')} UTC")
                with _lh2:
                    if st.button("↻ Refresh", key=f"reload_offers_{det.get('id', '')}",
                                 use_container_width=True, help="Re-fetch listings from Cardmarket"):
                        with st.spinner("Refreshing listings…"):
                            try:
                                from scraper.cardmarket_scraper import (
                                    create_session, fetch_offers_for_product,
                                )
                                sess = create_session()
                                off = fetch_offers_for_product(sess, cm_filt, max_offers=10)
                                st.session_state[offers_key] = off
                                st.session_state[offers_ts_key] = datetime.now(timezone.utc)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Could not refresh listings: {exc}")

                offers = st.session_state.get(offers_key)
                if not offers:
                    st.info("No listings found for this filter.")
                else:
                    rows_html = ""
                    for o in offers:
                        price_str = feur(o.get("price_eur"))
                        loc   = o.get("item_location", "")
                        flag  = o.get("item_location_flag", "")
                        lang_flag = o.get("language_flag", "")
                        seller_info = o.get("seller_info", "")
                        condition   = o.get("condition", "")
                        rows_html += (
                            f'<tr>'
                            f'<td><strong>{o.get("seller", "—")}</strong>'
                            f'<br><span style="font-size:0.68rem;color:#9ca3af">{seller_info}</span></td>'
                            f'<td style="text-align:center;font-size:1rem">{flag}<br>'
                            f'<span style="font-size:0.68rem;color:#7c87a8">{loc}</span></td>'
                            f'<td style="text-align:center;font-size:1rem">{lang_flag}<br>'
                            f'<span style="font-size:0.68rem;color:#7c87a8">{o.get("language", "")}</span></td>'
                            f'<td style="color:#64748b">{condition}</td>'
                            f'<td style="text-align:right;font-weight:600;color:#2d7d52">{price_str}</td>'
                            f'<td style="text-align:center;color:#9ca3af">{o.get("quantity", 1)}</td>'
                            f'</tr>'
                        )
                    st.markdown(
                        '<table class="ot"><thead><tr>'
                        '<th>Seller</th>'
                        '<th style="text-align:center">Item Country</th>'
                        '<th style="text-align:center">Language</th>'
                        '<th>Condition</th>'
                        '<th style="text-align:right">Price</th>'
                        '<th style="text-align:center">Qty</th>'
                        f'</tr></thead><tbody>{rows_html}</tbody></table>',
                        unsafe_allow_html=True,
                    )
                    st.caption(f"{len(offers)} listings shown")

# ==========================================================================
# TAB 3 – HISTORICAL ROI
# ==========================================================================
with tab_roi:
    hist_prods = [p for p in all_products if p.get("_is_historical") or p.get("_is_oop")]

    if not hist_prods:
        st.info("No historical / OOP products loaded.")
    else:
        rc1, rc2, rc3 = st.columns([3, 2, 2])
        with rc1:
            roi_search = st.selectbox(
                "rs",
                options=[""] + [p["name"] for p in hist_prods],
                index=0,
                format_func=lambda x: "Search…" if x == "" else x,
                label_visibility="collapsed",
                key="roi_search",
            )
        with rc2:
            roi_sort = st.selectbox(
                "sort",
                ["ROI %", "From Price", "MSRP", "Release Date"],
                label_visibility="collapsed",
                key="roi_sort",
            )
        with rc3:
            roi_types = sorted({p.get("type", "Other") for p in hist_prods})
            roi_type_f = st.multiselect(
                "tt", roi_types, default=roi_types,
                label_visibility="collapsed", key="roi_type",
                placeholder="Type…",
            )

        hf = [
            p for p in hist_prods
            if (not roi_search or p["name"] == roi_search)
            and (not roi_type_f or p.get("type", "Other") in roi_type_f)
        ]
        _rs_map = {
            "ROI %":        ("_roi",         True),
            "From Price":   ("_from",        True),
            "MSRP":         ("msrp_eur",     True),
            "Release Date": ("release_date", True),
        }
        rs_k, rs_r = _rs_map.get(roi_sort, ("_roi", True))
        hf = sorted(
            hf,
            key=lambda p: (
                p.get(rs_k) is None,
                p.get(rs_k) or "" if rs_k == "release_date" else (p.get(rs_k) or 0),
            ),
            reverse=rs_r,
        )

        # ── Visual card grid (top 8) ──────────────────────────────────────
        st.caption(f"{len(hf)} products — top 8 shown as cards")
        st.write("")
        g_cols = st.columns(4)
        for gi, gp in enumerate(hf[:8]):
            with g_cols[gi % 4]:
                img = gp.get("image_url")
                if img:
                    try:
                        st.image(_image_to_data_uri(img), use_container_width=True)
                    except Exception:
                        pass
                roi_v  = gp.get("_roi")
                rc_cls = "pc-neu" if roi_v is None else ("pc-pos" if roi_v >= 0 else "pc-neg")
                nm     = gp["name"]
                short  = nm[:34] + "…" if len(nm) > 34 else nm
                cm     = gp.get("cardmarket_url", "")
                link   = f'<a class="pc-link" href="{cm}{_CM_FILTER}" target="_blank">Cardmarket</a>' if cm else ""
                st.markdown(
                    f'<div class="pc-card">'
                    f'<div class="pc-name">{short}</div>'
                    f'<div class="pc-price">MSRP {feur(gp.get("msrp_eur"))} &rarr; {feur(gp.get("_from"))}</div>'
                    f'<div class="{rc_cls}">{froi(roi_v)}</div>'
                    f'{link}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.divider()

        # ── Full sortable table ───────────────────────────────────────────
        st.markdown("#### All historical products")
        roi_rows = [{
            "":              _image_to_data_uri(p["image_url"]) if p.get("image_url") else "",
            "Product":       p.get("name", ""),
            "Type":          p.get("type", "—"),
            "MSRP":          p.get("msrp_eur"),
            "From (BE·NL·DE)": p.get("_from"),
            "ROI %":         p.get("_roi"),
            "Released":      (p.get("release_date") or "")[:7],
            "OOP":           p.get("_oop_display", "?"),
            "View":          (p.get("cardmarket_url", "") + _CM_FILTER) if p.get("cardmarket_url") else "",
        } for p in hf]

        if roi_rows:
            st.dataframe(
                pd.DataFrame(roi_rows),
                use_container_width=True, hide_index=True, height=480,
                column_config={
                    "":              st.column_config.ImageColumn("", width="small"),
                    "Product":       st.column_config.TextColumn("Product", width="large"),
                    "Type":          st.column_config.TextColumn("Type", width="small"),
                    "MSRP":          st.column_config.NumberColumn("MSRP", format="€%.2f", width="small"),
                    "From (BE·NL·DE)": st.column_config.NumberColumn("From (BE·NL·DE)", format="€%.2f", width="medium"),
                    "ROI %":         st.column_config.NumberColumn("ROI %", format="%.0f%%", width="small"),
                    "Released":      st.column_config.TextColumn("Released", width="small"),
                    "OOP":           st.column_config.TextColumn("OOP", width="small"),
                    "View":          st.column_config.LinkColumn("Cardmarket", display_text="View", width="small"),
                },
            )

# ==========================================================================
# TAB 4 – PRICE HISTORY
# ==========================================================================
with tab_hist:
    if not HISTORY_PATH.exists():
        st.info(
            "No price history yet.\n\n"
            "Run **Refresh Prices** to start building price history, "
            "or from terminal:\n```\npython scraper/cardmarket_scraper.py\n```"
        )
    else:
        hist_df = pd.read_csv(HISTORY_PATH, parse_dates=["timestamp"])
        id_to_name = {p["id"]: p["name"] for p in all_products if "id" in p}

        pid_list  = hist_df["product_id"].unique().tolist()
        name_list = [id_to_name.get(pid, pid) for pid in pid_list]

        hc1, hc2 = st.columns([3, 2])
        with hc1:
            sel_hn  = st.selectbox("Product", name_list, key="hist_prod")
            sel_hid = pid_list[name_list.index(sel_hn)]
        with hc2:
            M_LABELS = {
                "from_filtered_eur": "From (BE/NL/DE)",
                "from_eur":          "From (Global)",
                "price_trend_eur":   "Price Trend",
                "avg_30d_eur":       "30d Average",
                "avg_7d_eur":        "7d Average",
            }
            sel_m = st.multiselect(
                "Metrics", list(M_LABELS.keys()),
                default=["from_filtered_eur", "from_eur"],
                format_func=lambda x: M_LABELS.get(x, x),
                key="hist_metrics",
            )

        ph = hist_df[hist_df["product_id"] == sel_hid].sort_values("timestamp")
        if ph.empty:
            st.info("No data yet for this product.")
        else:
            COLORS = {
                "from_filtered_eur": "#7b8cde",
                "from_eur":          "#5a9e78",
                "price_trend_eur":   "#e8a87c",
                "avg_30d_eur":       "#a78bca",
                "avg_7d_eur":        "#74b8c8",
            }
            fig = go.Figure()
            for m in sel_m:
                if m in ph.columns:
                    fig.add_trace(go.Scatter(
                        x=ph["timestamp"], y=ph[m],
                        name=M_LABELS.get(m, m),
                        mode="lines+markers",
                        line=dict(color=COLORS.get(m, "#aaa"), width=2),
                        marker=dict(size=5),
                    ))
            fig.update_layout(
                title=dict(text=sel_hn, font=dict(size=13, color="#2c3354")),
                xaxis=dict(
                    title="Date", gridcolor="#e8ebf5",
                    linecolor="#e4e8f4", tickfont=dict(size=11, color="#7c87a8"),
                ),
                yaxis=dict(
                    title="Price (€)", gridcolor="#e8ebf5",
                    linecolor="#e4e8f4", tickfont=dict(size=11, color="#7c87a8"),
                ),
                hovermode="x unified",
                height=420,
                margin=dict(l=0, t=40, r=0, b=0),
                plot_bgcolor="#ffffff",
                paper_bgcolor="#f7f8fc",
                font=dict(family="Inter, sans-serif", color="#4b5275"),
                legend=dict(
                    bgcolor="#ffffff",
                    bordercolor="#e4e8f4",
                    borderwidth=1,
                    font=dict(size=11),
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                f"{len(ph)} scrape runs  ·  "
                f"first: {ph['timestamp'].min().date()}  ·  "
                f"latest: {ph['timestamp'].max().date()}"
            )
