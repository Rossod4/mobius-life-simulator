"""
Portfolio Builder Game - a fun, standalone activity built on the SAME simulation engine and
asset-class data as the main comparison tool (src/engine.py, data/asset_class_returns.csv), so a
player's constructed portfolio is scored on exactly the same probability-of-ruin metric the main
app uses - just with the player choosing the allocation and fees themselves, across the Mobius
fund store's own asset-class sub-categories (or, in the alternate mode, the finer individual
building blocks), instead of comparing two pre-built portfolios.

Streamlit auto-discovers this file from app/pages/ as a second page of the multipage app entered
via `streamlit run app/app.py` - no changes to app.py needed, and no data duplicated: everything
here reads the same data/ CSVs and PORTFOLIOS-adjacent helpers as the main page, so the two stay in
sync automatically.

Designed for a live group activity: each team plays on their OWN device against the same deployed
app URL. The leaderboard therefore persists to a shared Google Sheet if credentials are configured
(see README - "Persistent leaderboard setup"), falling back automatically to a local CSV on disk
(game_state/leaderboard.csv, gitignored - it's session runtime state, not source data) otherwise.
st.session_state alone won't do, since that's per-browser-tab and would leave every other team's
screen blank.

Styled with the real Mobius brand identity (Mobius Brand Identity Overview v1.02 - colours, logo
mark and Inter typeface, see the brand palette constants below and app/assets/mobius_logo_icon.png)
rather than an invented theme, while still being more playful than the main comparison tool (big
animated reveal card, medal leaderboard, confetti) since this page is a game, not a client-facing
pitch deck. Every colour on this page - including the probability-of-ruin green/amber/red, which
reuses the main app's own risk-colour coding so the one number that actually matters still reads
the same way in both places - is now derived from the brand's own palette (deepened where a raw
brand pastel wouldn't have enough contrast to read clearly), not a generic/invented one.
"""
from __future__ import annotations

import html
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import load_asset_returns, load_cpi, run_simulation, ClientProfile
from portfolios import AC, PORTFOLIOS, PORTFOLIO_META, DATA_DIR, EQUITY_CLASSES, asset_class_weights, COMPARISON_GROUPS

st.set_page_config(page_title="Mobius Wealth - Portfolio Builder Game", layout="wide", page_icon="🎮")

# Same risk colours as the main app's probability-of-ruin cards (app.py's ruin_color logic) -
# consistent meaning across both pages. Still a distinct set from the brand palette below since
# they carry a specific green/gold/red risk meaning a decorative brand colour can't override, but
# each is now derived from the matching brand secondary colour (Light Sage/Pale Yellow/Coral Red)
# deepened just enough for real contrast as text or white-on-colour backgrounds - not the generic
# traffic-light hues this used before.
COLOR_GOOD = "#3f7a5e"   # deepened Light Sage
COLOR_WARN = "#C9A227"   # deepened Pale Yellow (same value as app.py's MOBIUS_PALETTE)
COLOR_BAD = "#D94A4A"    # deepened Coral Red

# Real Mobius brand palette (Mobius Brand Identity Overview v1.02) - see README for the source
# PDF. Primary colours are Carbon Black + white; secondary colours are soft pastels used as
# accents, with Coral Red reserved for one or two high-impact moments rather than as a base
# colour, per the brand guide's own "used sparingly" instruction.
CARBON_BLACK = "#0E0F14"
GREY_900 = "#262936"
GREY_800 = "#404552"
GREY_700 = "#5C5E6B"
GREY_600 = "#787A87"
GREY_500 = "#9494A1"
GREY_400 = "#B0B0BA"
STEEL_GREY = "#CCCCD5"
GREY_200 = "#E0E0E8"
GREY_100 = "#F2F2FA"
LIGHT_SAGE = "#A4CDBB"
CLOUD_BLUE = "#B6B7E0"
PALE_PINK = "#F1DBD7"
PALE_YELLOW = "#F8F0C8"
CORAL_RED = "#FF6969"


@st.cache_data(show_spinner=False)
def _logo_data_uri() -> str:
    """Base64-encodes the brand logo mark once per process, so it can sit inline inside custom
    HTML (the hero banner) the way an <img> tag needs - Streamlit has no native way to place
    st.image inside a styled div. Cropped from the brand guide PDF, transparent background."""
    import base64
    logo_path = Path(__file__).resolve().parent.parent / "assets" / "mobius_logo_icon.png"
    return "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode("ascii")


st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {{
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
    }}

    /* Very light, mostly-white page wash - the brand guide is explicit that Mobius "should
       always feel like a black and white brand", so this stays deliberately understated rather
       than the colourful theme wash an earlier version of this page used. */
    [data-testid="stAppViewContainer"] {{
        background:
            radial-gradient(rgba(204,204,213,0.35) 1.5px, transparent 1.5px),
            linear-gradient(160deg, {GREY_100}, #ffffff 55%);
        background-size: 30px 30px, 100% 100%;
    }}

    div[data-testid="stButton"] > button[kind="primary"] {{
        font-family: 'Inter', sans-serif;
        font-size: 1.05rem;
        font-weight: 600;
        border-radius: 999px;
        background: {CORAL_RED};
        color: white;
        border: none;
        padding: 0.7rem 0;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover {{
        transform: scale(1.015);
        box-shadow: 0 6px 18px rgba(255, 105, 105, 0.4);
    }}
    /* Secondary buttons stay in the black/white core palette - Coral Red is reserved for the
       one primary call-to-action per the brand guide's "use sparingly" instruction. */
    div[data-testid="stButton"] > button:not([kind="primary"]) {{
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        border-radius: 999px;
        border: 2px solid {CARBON_BLACK};
        color: {CARBON_BLACK};
        transition: transform 0.15s ease, background 0.15s ease;
    }}
    div[data-testid="stButton"] > button:not([kind="primary"]):hover {{
        background: {GREY_100};
        transform: scale(1.015);
        color: {CARBON_BLACK};
    }}

    /* Card-wrap the leaderboard table so it feels like a designed panel rather than a plain
       spreadsheet grid (the allocation inputs below are sliders, not a data grid). */
    [data-testid="stDataFrame"] {{
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 4px 14px rgba(14, 15, 20, 0.06);
        border: 1px solid {STEEL_GREY};
    }}

    .step-row {{ display: flex; gap: 0.6rem; margin-bottom: 1.2rem; }}
    .step-pill {{
        flex: 1; text-align: center; padding: 0.55rem 0.5rem; border-radius: 999px;
        font-weight: 600; font-size: 0.85rem;
        border: 2px solid {STEEL_GREY}; color: {GREY_500};
        background: {GREY_100}; transition: all 0.2s ease;
    }}
    .step-pill.active {{
        border-color: {CARBON_BLACK}; color: white;
        background: {CARBON_BLACK};
        box-shadow: 0 4px 12px rgba(14, 15, 20, 0.25);
    }}
    .step-pill.done {{ border-color: {LIGHT_SAGE}; color: {COLOR_GOOD}; background: rgba(164,205,187,0.18); }}

    .game-hero {{
        position: relative;
        overflow: hidden;
        background: {CARBON_BLACK};
        border-radius: 18px;
        padding: 1.8rem 2rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 8px 24px rgba(14, 15, 20, 0.3);
    }}
    .game-hero::before {{
        content: "";
        position: absolute;
        inset: -20%;
        background:
            radial-gradient(ellipse 40% 60% at 12% 15%, rgba(255,105,105,0.35), transparent 60%),
            radial-gradient(ellipse 45% 65% at 42% 5%, rgba(182,183,224,0.4), transparent 60%),
            radial-gradient(ellipse 50% 70% at 78% 90%, rgba(164,205,187,0.4), transparent 60%),
            radial-gradient(ellipse 40% 55% at 98% 35%, rgba(241,219,215,0.3), transparent 60%);
        mix-blend-mode: screen;
        pointer-events: none;
    }}
    .game-hero .hero-title {{
        position: relative;
        display: flex; align-items: center; gap: 0.75rem;
    }}
    .game-hero .hero-title img {{
        height: 2.1rem; width: auto;
        animation: wobble 2.6s ease-in-out infinite;
    }}
    @keyframes wobble {{
        0%, 100% {{ transform: rotate(0deg); }}
        25% {{ transform: rotate(-6deg); }}
        75% {{ transform: rotate(6deg); }}
    }}
    .game-hero h1 {{
        color: white;
        font-weight: 500;
        font-size: 2.1rem;
        margin: 0;
    }}
    .game-hero p {{
        position: relative;
        color: rgba(255,255,255,0.85);
        font-size: 0.98rem;
        margin: 0.75rem 0 0 0;
        max-width: 60rem;
    }}

    .howto-row {{ display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1.2rem; }}
    .howto-card {{
        flex: 1 1 200px;
        border-radius: 14px;
        padding: 0.9rem 1rem;
        background: white;
        border: 1px solid {STEEL_GREY};
    }}
    .howto-card .num {{
        display: inline-flex; align-items: center; justify-content: center;
        width: 1.6rem; height: 1.6rem; border-radius: 50%;
        background: {CARBON_BLACK};
        color: white; font-weight: 700; font-size: 0.85rem;
        margin-bottom: 0.4rem;
    }}
    .howto-card .txt {{ font-size: 0.85rem; color: {GREY_700}; }}

    .stats-banner {{
        display: flex; flex-wrap: wrap; gap: 1.5rem; justify-content: center;
        border-radius: 14px; padding: 0.75rem 1rem; margin-bottom: 1.2rem;
        background: {PALE_YELLOW};
        border: 1px solid {STEEL_GREY};
        font-size: 0.9rem; font-weight: 500; color: {CARBON_BLACK};
    }}

    .stat-card {{
        border: 1px solid {STEEL_GREY};
        border-radius: 14px;
        padding: 0.85rem 1rem;
        text-align: center;
        background: white;
        transition: transform 0.15s ease;
    }}
    .stat-card:hover {{ transform: translateY(-2px); }}
    .stat-card .label {{
        font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.05em; color: {GREY_600};
    }}
    .stat-card .value {{
        font-size: 1.6rem; font-weight: 600; line-height: 1.3; color: {CARBON_BLACK};
    }}
    .stat-card .comment {{
        font-size: 0.78rem; font-style: italic; opacity: 0.75; margin-top: 0.35rem;
    }}

    @keyframes popIn {{
        0% {{ transform: scale(0.4); opacity: 0; }}
        60% {{ transform: scale(1.12); opacity: 1; }}
        80% {{ transform: scale(0.96); }}
        100% {{ transform: scale(1); }}
    }}
    @keyframes numberPop {{
        0% {{ transform: scale(0.3); opacity: 0; }}
        50% {{ transform: scale(1.25); opacity: 1; }}
        75% {{ transform: scale(0.9); }}
        100% {{ transform: scale(1); }}
    }}
    .result-card {{
        border-radius: 20px;
        padding: 1.8rem 2rem;
        text-align: center;
        color: white;
        animation: popIn 0.5s cubic-bezier(.34,1.56,.64,1);
        box-shadow: 0 10px 28px rgba(0,0,0,0.18);
        margin-bottom: 1rem;
    }}
    .result-card .big-number {{
        font-weight: 700;
        font-size: 4.6rem;
        line-height: 1.1;
        display: inline-block;
        animation: numberPop 0.6s 0.15s cubic-bezier(.34,1.56,.64,1) backwards;
        text-shadow: 0 4px 18px rgba(0,0,0,0.25);
    }}
    .result-card .tagline {{
        font-size: 1.05rem;
        opacity: 0.95;
        margin-top: 0.3rem;
    }}

    .battle-card {{
        border-radius: 14px;
        padding: 1rem;
        text-align: center;
        border: 2px solid {STEEL_GREY};
        background: white;
    }}
    .battle-card.winner {{ border-color: {LIGHT_SAGE}; background: rgba(164,205,187,0.15); }}
    .battle-card .name {{ font-size: 0.8rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.03em; color: {GREY_600}; }}
    .battle-card .pct {{ font-size: 1.7rem; font-weight: 700; color: {CARBON_BLACK}; }}

    .badge-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: center;
        margin: 0.75rem 0 1rem 0; }}
    .badge-pill {{
        font-size: 0.85rem;
        font-weight: 600;
        padding: 0.35rem 0.9rem;
        border-radius: 999px;
        background: {CARBON_BLACK};
        color: white;
    }}

    .suspense-text {{
        text-align: center;
        font-size: 1.1rem;
        font-weight: 500;
        color: {CARBON_BLACK};
        padding: 1rem 0;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

GAME_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "game_state"
GAME_STATE_DIR.mkdir(exist_ok=True)
LEADERBOARD_CSV = GAME_STATE_DIR / "leaderboard.csv"
LEADERBOARD_COLUMNS = ["Time", "Team", "Mode", "Probability of ruin", "Median annual return %",
                        "Asset classes used", "Allocation"]

SUSPENSE_MESSAGES = [
    "🎲 Testing your portfolio against 2,000 possible futures...",
    "📉 Simulating market crashes...",
    "📈 Simulating bull runs...",
    "🧮 Crunching the numbers...",
]


@st.cache_data(show_spinner=False)
def _cached_load_asset_returns(_mtime: float) -> pd.DataFrame:
    return load_asset_returns()


_asset_returns_mtime = (DATA_DIR / "asset_class_returns.csv").stat().st_mtime
asset_df = _cached_load_asset_returns(_asset_returns_mtime)
cpi = load_cpi(asset_df)


@st.cache_data(show_spinner=False)
def _benchmark_result(name, _asset_df, _cpi, profile):
    """Cached per (portfolio name, profile) - independent of any player's own allocation, so every
    team playing with the same host-set client profile shares one cached run instead of
    re-simulating Better on every single reveal click. Returns the full SimResult (not just
    prob_ruin) so its simulated paths can feed the fan chart too. Only ever called with "Better" -
    deliberately not any competitor portfolio, since this is an internal Mobius game."""
    return run_simulation(name, _asset_df, _cpi, profile, method="stationary_block",
                           n_sims=2000, seed=42)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _median_cagr(paths, starting_pot, horizon_years):
    """Median (typical) simulated annualised return, derived from the median final pot value vs
    the starting pot - the same 'typical outcome' concept as the median line on a fan chart,
    collapsed into one headline % figure."""
    median_final = float(np.median(paths[:, -1]))
    if starting_pot <= 0 or horizon_years <= 0:
        return 0.0
    return (median_final / starting_pot) ** (1.0 / horizon_years) - 1.0


@st.cache_resource(show_spinner=False)
def _gsheet_ws_cached():
    """Live gspread Worksheet connection, memoized once per server process (a connection isn't
    picklable/comparable data, hence cache_resource not cache_data). Only called once secrets
    are confirmed present - see _gsheet_ws()."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(st.secrets["leaderboard_sheet_key"]).sheet1
    if not ws.get_all_values():
        ws.append_row(LEADERBOARD_COLUMNS)
    return ws


def _gsheet_ws():
    """Returns a gspread Worksheet if Google Sheets credentials are configured in st.secrets
    (see README - 'Persistent leaderboard setup'), else None - every caller below falls back to
    the local game_state/leaderboard.csv file, which is fine for local dev/testing but resets on
    every Streamlit Cloud restart/redeploy and isn't safe under genuinely concurrent writes."""
    try:
        if "gcp_service_account" not in st.secrets or "leaderboard_sheet_key" not in st.secrets:
            return None
    except Exception:
        return None
    try:
        return _gsheet_ws_cached()
    except Exception:
        return None


def _leaderboard_mode() -> str:
    return ("🟢 Google Sheets (persistent, survives restarts)" if _gsheet_ws() is not None
            else "🟡 Local file only (resets on app restart/redeploy - see README)")


def _load_leaderboard() -> pd.DataFrame:
    ws = _gsheet_ws()
    if ws is not None:
        try:
            df = pd.DataFrame(ws.get_all_records())
            return df if not df.empty else pd.DataFrame(columns=LEADERBOARD_COLUMNS)
        except Exception:
            pass  # fall through to the local file if the API call itself fails
    if LEADERBOARD_CSV.exists():
        try:
            return pd.read_csv(LEADERBOARD_CSV)
        except pd.errors.EmptyDataError:
            pass
    return pd.DataFrame(columns=LEADERBOARD_COLUMNS)


def _append_leaderboard(row: dict):
    ws = _gsheet_ws()
    if ws is not None:
        try:
            ws.append_row([row.get(c, "") for c in LEADERBOARD_COLUMNS])
            return
        except Exception:
            pass  # fall through to the local file if the API call itself fails
    df = pd.concat([_load_leaderboard(), pd.DataFrame([row])], ignore_index=True)
    df.to_csv(LEADERBOARD_CSV, index=False)


def _clear_leaderboard():
    ws = _gsheet_ws()
    if ws is not None:
        try:
            ws.clear()
            ws.append_row(LEADERBOARD_COLUMNS)
            return
        except Exception:
            pass
    pd.DataFrame(columns=LEADERBOARD_COLUMNS).to_csv(LEADERBOARD_CSV, index=False)


def _stat_card(label, value, color=None, icon=None, comment=None):
    color_style = f"color:{color};" if color else ""
    icon_html = f"{icon} " if icon else ""
    comment_html = f"<div class='comment'>{comment}</div>" if comment else ""
    st.markdown(
        f"<div class='stat-card'><div class='label'>{icon_html}{label}</div>"
        f"<div class='value' style='{color_style}'>{value}</div>{comment_html}</div>",
        unsafe_allow_html=True,
    )


def _return_comment(median_return):
    pct = median_return * 100
    if pct < -2:
        return "😬 Shrinking faster than milk left out overnight."
    elif pct < 0:
        return "📉 Technically still losing, just... politely."
    elif pct < 2:
        return "🐢 Slow and steady. Very steady."
    elif pct < 5:
        return "🙂 Perfectly respectable. Nothing to write home about."
    elif pct < 8:
        return "😎 Now we're talking."
    else:
        return "🚀 To the moon (or a very lucky draw of markets)."


def _outcome_comment(median_outcome, starting_pot):
    if starting_pot <= 0:
        return ""
    ratio = median_outcome / starting_pot
    if ratio < 0.05:
        return "💸 Down to fumes."
    elif ratio < 0.5:
        return "😰 Noticeably thinner than you started."
    elif ratio < 1.0:
        return "🙂 Smaller, but still standing."
    elif ratio < 2.0:
        return "👍 Held its own and then some."
    elif ratio < 4.0:
        return "🏰 You could buy a small castle."
    else:
        return "🤑 Someone's leaving a very generous inheritance."


def _tier(prob_ruin):
    if prob_ruin < 0.05:
        return "Excellent", "🏆", COLOR_GOOD, "Retirement royalty. This plan just about never runs dry."
    elif prob_ruin < 0.15:
        return "Good", "✅", COLOR_GOOD, "A solid, sensible plan. Nice work."
    elif prob_ruin < 0.30:
        return "Risky", "⚠️", COLOR_WARN, "Living a little dangerously - some futures don't end well."
    else:
        return "High risk", "💀", COLOR_BAD, "Back to the drawing board - this pot runs out a lot."


def _badges(weights, custom_fee, selected_count, max_classes):
    """Flair tags based on HOW a portfolio was built, not the score - separate from the tier
    verdict (which is purely about the outcome), these reward specific construction choices."""
    equity_weight = float(weights[weights.index.isin(EQUITY_CLASSES)].sum())
    tags = []
    if equity_weight >= 0.8:
        tags.append("🎲 Risk Taker")
    elif equity_weight <= 0.2:
        tags.append("🛡️ Ultra Safe")
    elif 0.35 <= equity_weight <= 0.65:
        tags.append("⚖️ Balanced")
    if custom_fee <= 0.0015:
        tags.append("💰 Fee Hawk")
    if selected_count == max_classes:
        tags.append("🌐 Diversifier")
    return tags


# The Mobius fund store's own "Asset Class Sub-category" list (per the platform's filter panel),
# each mapped to the underlying long-history series in data/asset_class_returns.csv that best
# represents it - a category mapped to more than one series (e.g. "Equity" -> developed + emerging)
# has its assigned weight split evenly across its constituents when a player's portfolio is scored.
# A category mapped to None has NO return series anywhere in this model yet (these are mostly
# private-market/LDI-style categories the fund store lists but that aren't in the Bloomberg data
# behind this simulator) - shown in the game as "coming soon" rather than faked with invented
# numbers, since the whole point of this game is that the probability-of-ruin answer is real.
FUND_STORE_MAP: dict[str, list[str] | None] = {
    "Commodities": ["Commodities"],
    "Corporate Bonds": ["US HY Corp Bond", "EM Corp Bond"],
    "Equity": ["Global Equities", "EM Equities"],
    "Gilts": ["UK Gilts All Stocks", "UK Gilts 15yr+", "UK Gilts <5yr"],
    "Index Linked Gilts": ["UK Index-Linked Gilts"],
    "Infrastructure": ["Infrastructure"],
    "LDI": None,
    "Money Markets": ["Cash"],
    "Multi Asset": None,
    "Multi Asset Credit": None,
    "Overseas Government Bonds": ["Global Bonds", "US Treasuries 20yr+"],
    "Private Credit": None,
    "Private Equity": None,
    "Private Markets Multi Asset": None,
    "Property": ["REITs", "US Prop REITS"],
    "Real Assets": None,
    "Securitised Credit": ["Securitised Credit"],
}
AVAILABLE_CATEGORIES = [c for c, v in FUND_STORE_MAP.items() if v is not None]
UNAVAILABLE_CATEGORIES = [c for c, v in FUND_STORE_MAP.items() if v is None]

st.markdown(
    f"<div class='game-hero'>"
    f"<div class='hero-title'><img src='{_logo_data_uri()}' alt='Mobius'><h1>Build Your Own Portfolio</h1></div>"
    "<p>Assign weightings (and fees) across asset classes, then find out how likely your portfolio "
    "is to run out of money in retirement. Runs on the exact same simulation engine and market data "
    "as the main Mobius Wealth comparison tool - nothing here is a simplified stand-in. Play on your "
    "own device - everyone's score lands on the shared leaderboard at the bottom of the page.</p>"
    "</div>",
    unsafe_allow_html=True,
)

_HOWTO_STEPS = [
    ("1️⃣", "Pick your mode", "Fund store categories (broad) or individual building blocks (finer) - your call."),
    ("2️⃣", "Build your mix", "Assign a weight and a fee to each asset class you want to hold, until you hit 100%."),
    ("3️⃣", "Hit reveal", "Only then do you find out your probability of ruin - no peeking beforehand."),
    ("4️⃣", "Climb the board", "Your score lands on the shared leaderboard below - everyone playing sees it."),
]
st.markdown(
    "<div class='howto-row'>" + "".join(
        f"<div class='howto-card'><div class='num'>{n}</div><br>"
        f"<b>{title}</b><div class='txt'>{desc}</div></div>"
        for n, title, desc in _HOWTO_STEPS
    ) + "</div>",
    unsafe_allow_html=True,
)

_lb_for_banner = _load_leaderboard()
if _lb_for_banner.empty:
    st.markdown(
        "<div class='stats-banner'>🌱 No portfolios built yet - be the first!</div>",
        unsafe_allow_html=True,
    )
else:
    _n_plays = len(_lb_for_banner)
    _n_teams = _lb_for_banner["Team"].nunique()
    _avg_ruin = _lb_for_banner["Probability of ruin"].mean()
    _best_row = _lb_for_banner.loc[_lb_for_banner["Probability of ruin"].idxmin()]
    st.markdown(
        "<div class='stats-banner'>"
        f"<span>🎲 {_n_plays} portfolio{'s' if _n_plays != 1 else ''} built</span>"
        f"<span>👥 {_n_teams} team{'s' if _n_teams != 1 else ''} playing</span>"
        f"<span>📊 avg probability of ruin: {_avg_ruin:.1f}%</span>"
        f"<span>🏆 best so far: {_best_row['Team']} ({_best_row['Probability of ruin']:.1f}%)</span>"
        "</div>",
        unsafe_allow_html=True,
    )

with st.expander("⚙️ Game setup (host controls)", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        age = st.number_input("Starting age", 40, 90, 65)
    with c2:
        horizon = st.slider("Time horizon (years)", 5, 40, 30)
    with c3:
        pot = st.number_input("Starting pot (£)", 10_000, 10_000_000, 500_000, step=10_000)
    with c4:
        spend = st.number_input("Desired annual spend (£)", 1_000, 500_000, 20_000, step=1_000)
    max_classes = st.number_input(
        "Max number of asset classes a player can use", 1, 26, 6,
        help="Forces harder trade-offs instead of just spreading weight across everything on offer.",
    )
    max_fee_pct = st.number_input(
        "Max weighted fee allowed (% pa)", 0.0, 3.0, 0.20, step=0.01,
        help="A second constraint alongside the asset-class cap - forces a genuine cost-vs-"
             "diversification trade-off instead of just picking the priciest option everywhere.",
    )
    st.divider()
    st.caption(f"Leaderboard storage: {_leaderboard_mode()}")
    st.caption(f"Leaderboard has {len(_load_leaderboard())} entries.")
    if st.button("🗑️ Clear leaderboard (start a new game)"):
        _clear_leaderboard()
        st.rerun()

granularity = st.radio(
    "🧩 Asset classes",
    ["Fund store categories", "Individual building blocks"],
    horizontal=True,
    help="Fund store categories: the same Asset Class Sub-category list as the Mobius fund store "
         "platform. Individual building blocks: the finer underlying asset-class series, including "
         "the specific equity/credit/alternatives strategies used in the Better portfolio.",
)
is_fund_store = granularity == "Fund store categories"
labels = AVAILABLE_CATEGORIES if is_fund_store else list(AC.keys())
result_key = f"game_result_{granularity}"

_current_step = "reveal" if st.session_state.get(result_key) is not None else "build"
st.markdown(
    "<div class='step-row'>"
    f"<div class='step-pill{' active' if _current_step == 'build' else ' done'}'>🏗️ Build</div>"
    f"<div class='step-pill{' active' if _current_step == 'reveal' else ''}'>🎉 Reveal</div>"
    "<div class='step-pill'>🏆 Leaderboard</div>"
    "</div>",
    unsafe_allow_html=True,
)

team_name = st.text_input("🏷️ Team / player name", key="team_name",
                           help="Shown on the leaderboard - pick something your team will recognise.")

st.markdown("#### 🏗️ Your allocation")
st.caption("Drag a slider for each asset class you want to hold (they must add up to 100%), and set "
           "the annual fee you're assuming for each. Leave a slider at 0% to leave it out entirely.")

weight_values, fee_values = [], []
header_l, header_w, header_f = st.columns([2.5, 5.5, 1.5])
with header_w:
    st.caption("WEIGHT %")
with header_f:
    st.caption("FEE % PA")
for label in labels:
    row_l, row_w, row_f = st.columns([2.5, 5.5, 1.5])
    with row_l:
        st.markdown(f"<div style='padding-top:0.6rem;'>{label}</div>", unsafe_allow_html=True)
    with row_w:
        w = st.slider(label, 0.0, 100.0, 0.0, step=0.5, key=f"w_{granularity}_{label}",
                       label_visibility="collapsed")
    with row_f:
        f = st.number_input(label, 0.0, 3.0, 0.10, step=0.01, key=f"f_{granularity}_{label}",
                             label_visibility="collapsed")
    weight_values.append(w)
    fee_values.append(f)

edited = pd.DataFrame({"Asset class": labels, "Weight %": weight_values, "Fee % pa": fee_values})

if is_fund_store and UNAVAILABLE_CATEGORIES:
    st.caption(
        "🚧 Not selectable yet (no return data in the model): " + ", ".join(UNAVAILABLE_CATEGORIES)
        + " — these are on the fund store's own asset-class list but don't have historical return "
          "series behind them here, so they're left out rather than guessed at."
    )

total_weight = float(edited["Weight %"].sum())
selected_count = int((edited["Weight %"] > 0).sum())
live_fee_pct = float((edited["Weight %"] * edited["Fee % pa"]).sum() / total_weight) if total_weight > 0 else 0.0
weights_ok = abs(total_weight - 100.0) < 0.51
count_ok = 0 < selected_count <= max_classes
fee_ok = live_fee_pct <= max_fee_pct + 1e-9
name_ok = bool(team_name.strip())
can_reveal = weights_ok and count_ok and fee_ok and name_ok

if total_weight <= 0:
    build_stage = "⬜ Nothing built yet"
elif total_weight < 50:
    build_stage = "🧱 Just getting started..."
elif total_weight < 100:
    build_stage = "🏗️ Halfway there..."
elif weights_ok:
    build_stage = "✅ Ready to build!"
else:
    build_stage = "⚠️ Over 100% - trim something back"

st.progress(min(total_weight / 100.0, 1.0))
st.caption(build_stage)
progress_col, count_col, fee_col, name_col = st.columns(4)
with progress_col:
    _stat_card("Total allocated", f"{total_weight:.1f}% / 100%",
               COLOR_GOOD if weights_ok else None, icon="🧮")
with count_col:
    _stat_card("Asset classes used", f"{selected_count} / {max_classes}",
               COLOR_GOOD if count_ok else COLOR_BAD if selected_count else None, icon="🧩")
with fee_col:
    _stat_card("Weighted fee", f"{live_fee_pct:.2f}% / {max_fee_pct:.2f}%",
               COLOR_GOOD if fee_ok else COLOR_BAD if total_weight > 0 else None, icon="💷")
with name_col:
    _stat_card("Team name", html.escape(team_name.strip()) if name_ok else "Not set yet",
               COLOR_GOOD if name_ok else COLOR_BAD, icon="🏷️")

if not weights_ok:
    st.warning("Your weights need to add up to 100% before you can build your portfolio.")
if not count_ok and selected_count > 0:
    st.warning(f"You've used {selected_count} asset classes - the limit for this game is {max_classes}. "
               f"Zero out some rows to get under the limit.")
if not fee_ok and total_weight > 0:
    st.warning(f"Your weighted fee is {live_fee_pct:.2f}% pa - the limit for this game is "
               f"{max_fee_pct:.2f}% pa. Swap in some cheaper asset classes.")
if not name_ok:
    st.warning("Enter a team / player name above so your score can go on the leaderboard.")

reveal = st.button("🎯 Build my portfolio & reveal my score", type="primary",
                    disabled=not can_reveal, use_container_width=True)

if reveal:
    rows = edited[edited["Weight %"] > 0]
    allocation_str = ", ".join(f"{r['Asset class']} {r['Weight %']:.0f}%" for _, r in rows.iterrows())
    ac_vals, w_vals, fee_vals = [], [], []
    for _, r in rows.iterrows():
        constituents = FUND_STORE_MAP[r["Asset class"]] if is_fund_store else [r["Asset class"]]
        share = r["Weight %"] / len(constituents)
        for ac in constituents:
            ac_vals.append(ac)
            w_vals.append(share)
            fee_vals.append(r["Fee % pa"])

    weights = pd.Series(w_vals, index=ac_vals, dtype=float) / total_weight
    weights = weights.groupby(level=0).sum()  # guards against two rows resolving to the same series
    fees = pd.Series(fee_vals, index=ac_vals, dtype=float).groupby(level=0).mean() / 100.0
    custom_fee = float((weights * fees.reindex(weights.index)).sum())

    suspense_slot = st.empty()
    for msg in SUSPENSE_MESSAGES:
        suspense_slot.markdown(f"<div class='suspense-text'>{msg}</div>", unsafe_allow_html=True)
        time.sleep(0.45)

    profile = ClientProfile(starting_age=age, horizon_years=horizon, starting_pot=float(pot),
                             initial_annual_spend=float(spend))
    result = run_simulation("Your portfolio", asset_df, cpi, profile, method="stationary_block",
                             n_sims=2000, seed=42, custom_weights=weights, custom_fee=custom_fee)
    suspense_slot.empty()

    median_return = _median_cagr(result.paths, float(pot), horizon)
    st.session_state[result_key] = result.prob_ruin
    st.session_state[f"game_return_{granularity}"] = median_return
    st.session_state[f"game_paths_{granularity}"] = result.paths
    st.session_state[f"game_weights_{granularity}"] = weights
    st.session_state[f"game_badges_{granularity}"] = _badges(weights, custom_fee, selected_count, max_classes)
    _append_leaderboard({
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Team": team_name.strip(),
        "Mode": granularity,
        "Probability of ruin": round(result.prob_ruin * 100, 2),
        "Median annual return %": round(median_return * 100, 2),
        "Asset classes used": selected_count,
        "Allocation": allocation_str,
    })

if st.session_state.get(result_key) is not None:
    prob_ruin = st.session_state[result_key]
    st.divider()
    tier, emoji, color, tagline = _tier(prob_ruin)
    st.markdown(
        f"<div class='result-card' style='background:linear-gradient(135deg, {color}, {color}cc);'>"
        f"<div style='font-size:0.9rem; font-weight:700; text-transform:uppercase; "
        f"letter-spacing:0.06em; opacity:0.9;'>{emoji} {tier}</div>"
        f"<div class='big-number'>{prob_ruin * 100:.1f}%</div>"
        f"<div style='font-size:0.85rem; opacity:0.85;'>probability of ruin</div>"
        f"<div class='tagline'>{tagline}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if prob_ruin < 0.15:
        st.balloons()

    median_return = st.session_state.get(f"game_return_{granularity}", 0.0)
    median_outcome = float(np.median(st.session_state[f"game_paths_{granularity}"][:, -1]))
    return_col1, return_col2 = st.columns(2)
    with return_col1:
        _stat_card("Median annual return", f"{median_return * 100:+.1f}%",
                   COLOR_GOOD if median_return >= 0 else COLOR_BAD, icon="📈",
                   comment=_return_comment(median_return))
    with return_col2:
        _stat_card("Median outcome (final pot)", f"£{median_outcome:,.0f}", icon="💰",
                   comment=_outcome_comment(median_outcome, float(pot)))

    badges = st.session_state.get(f"game_badges_{granularity}", [])
    if badges:
        st.markdown(
            "<div class='badge-row'>" + "".join(f"<span class='badge-pill'>{b}</span>" for b in badges)
            + "</div>",
            unsafe_allow_html=True,
        )

    profile = ClientProfile(starting_age=age, horizon_years=horizon, starting_pot=float(pot),
                             initial_annual_spend=float(spend))
    better_result = _benchmark_result("Better", asset_df, cpi, profile)
    better_ruin = better_result.prob_ruin

    st.markdown("#### ⚔️ How you compare")
    st.caption("Benchmarked against Mobius Better - the tool's own most diversified construction, "
               "not a competitor's fund - as a guide to how well (or badly) you did.")
    contenders = [
        ("You", prob_ruin),
        (PORTFOLIO_META.get("Better", {}).get("DisplayName", "Mobius Better"), better_ruin),
    ]
    best_ruin = min(p for _, p in contenders)
    bcols = st.columns(2)
    for col, (label, p) in zip(bcols, contenders):
        with col:
            is_winner = p == best_ruin
            crown = "👑 " if is_winner else ""
            st.markdown(
                f"<div class='battle-card{' winner' if is_winner else ''}'>"
                f"<div class='name'>{crown}{label}</div>"
                f"<div class='pct'>{p * 100:.1f}%</div></div>",
                unsafe_allow_html=True,
            )
    beat_better = prob_ruin < better_ruin
    if beat_better:
        st.success("🎉 You beat Mobius Better - the tool's own most diversified construction. Impressive.")
    else:
        st.info("📉 Mobius Better currently beats you - room to improve.")

    st.markdown("#### 📊 How your pot could evolve")
    st.caption("Interactive - hover for exact values, drag to zoom. The bold line is each portfolio's "
               "median (typical) simulated outcome; the shaded band is the middle 50% of simulated futures.")
    fan = go.Figure()
    fan_series = [
        ("You", COLOR_GOOD if prob_ruin < 0.15 else COLOR_WARN if prob_ruin < 0.30 else COLOR_BAD,
         st.session_state[f"game_paths_{granularity}"]),
        # A deepened Cloud Blue for Mobius's own line - the brand's raw Cloud Blue (#B6B7E0) is too
        # pale to read clearly as a chart line at normal width, so this keeps the same hue family
        # while giving it enough contrast to actually see.
        (PORTFOLIO_META.get("Better", {}).get("DisplayName", "Mobius Better"), "#5B8FA8",
         better_result.paths),
    ]
    years_axis = np.arange(horizon + 1)
    for label, fan_color, paths in fan_series:
        q25, q50, q75 = (np.percentile(paths, q, axis=0) for q in (25, 50, 75))
        fan.add_trace(go.Scatter(x=years_axis, y=q75, line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fan.add_trace(go.Scatter(x=years_axis, y=q25, fill="tonexty", line=dict(width=0), showlegend=False,
                                  hoverinfo="skip", fillcolor=_hex_to_rgba(fan_color, 0.18)))
        fan.add_trace(go.Scatter(x=years_axis, y=q50, mode="lines", name=label,
                                  line=dict(width=3, color=fan_color)))
    fan.update_layout(
        xaxis_title="Year", yaxis_title="Portfolio value (£)", height=420,
        margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fan, use_container_width=True)

    st.markdown("#### 🧩 How diversification made the difference")
    you_weights = st.session_state[f"game_weights_{granularity}"]
    better_weights = asset_class_weights("Better")

    def _grouped_weights(w):
        """Rolls asset-class-level weights up onto the same like-for-like comparison groups the
        main app uses (portfolios.COMPARISON_GROUPS), so a player's fund-store category picks and
        Better's own holding-level construction can be compared on equal terms even though they're
        built from completely different underlying labels."""
        groups = w.index.map(lambda c: COMPARISON_GROUPS.get(c, c))
        return w.groupby(groups).sum()

    you_grouped = _grouped_weights(you_weights)
    better_grouped = _grouped_weights(better_weights)
    all_groups = sorted(set(you_grouped.index) | set(better_grouped.index),
                         key=lambda g: -better_grouped.get(g, 0))

    div_fig = go.Figure()
    div_fig.add_trace(go.Bar(x=all_groups, y=[you_grouped.get(g, 0) * 100 for g in all_groups],
                              name="You", marker_color=CORAL_RED))
    div_fig.add_trace(go.Bar(
        x=all_groups, y=[better_grouped.get(g, 0) * 100 for g in all_groups],
        name=PORTFOLIO_META.get("Better", {}).get("DisplayName", "Mobius Better"), marker_color="#5B8FA8",
    ))
    div_fig.update_layout(
        barmode="group", yaxis_title="Weight (%)", height=360,
        margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
        legend=dict(orientation="h", y=-0.3), xaxis_tickangle=-30,
    )
    st.plotly_chart(div_fig, use_container_width=True)

    you_class_count = int((you_grouped > 0.001).sum())
    better_class_count = int((better_grouped > 0.001).sum())
    if not beat_better:
        st.info(
            f"🧩 Mobius Better spreads its 100% across **{better_class_count} asset classes**; you used "
            f"**{you_class_count}**. That spread is a big part of why it holds up better here - when one "
            "asset class has a bad run, the others usually aren't all falling at the same time, so the "
            "pot doesn't take the full hit."
        )
    else:
        st.info(
            f"🧩 You used **{you_class_count} asset class{'es' if you_class_count != 1 else ''}** against "
            f"Mobius Better's **{better_class_count}** - and still came out ahead this time. Diversification "
            "improves your odds across many possible futures; it doesn't guarantee the outcome of any "
            "single one."
        )

    if st.button("🔁 Build another portfolio"):
        del st.session_state[result_key]
        st.rerun()

st.divider()
st.markdown("### 🏆 Leaderboard")
st.caption(_leaderboard_mode())
leaderboard = _load_leaderboard()
if st.button("🔄 Refresh leaderboard"):
    st.rerun()
if leaderboard.empty:
    st.caption("No scores yet - be the first to build a portfolio.")
else:
    ranked = leaderboard.sort_values("Probability of ruin").reset_index(drop=True)
    medals = ["🥇", "🥈", "🥉"]
    ranked.insert(0, "Rank", [medals[i] if i < 3 else str(i + 1) for i in range(len(ranked))])
    current = team_name.strip().lower()
    if current:
        ranked["Team"] = ranked["Team"].apply(lambda t: f"👉 {t}" if t.strip().lower() == current else t)

    # Podium tints derived from the brand palette rather than generic gold/silver/bronze web
    # colours: deepened Pale Yellow for 1st, Steel Grey for 2nd (already named "Steel" - a neat
    # fit for silver), deepened Pale Pink for 3rd.
    _row_colors = {0: "rgba(201,162,39,0.20)", 1: "rgba(204,204,213,0.35)", 2: "rgba(217,143,163,0.20)"}

    def _highlight_podium(row):
        style = f"background-color: {_row_colors[row.name]}" if row.name in _row_colors else ""
        return [style] * len(row)

    display_df = ranked.drop(columns=["Allocation"], errors="ignore")
    st.dataframe(display_df.style.apply(_highlight_podium, axis=1), hide_index=True, use_container_width=True)

    if st.button("🏅 Reveal the winning allocation"):
        winner = ranked.iloc[0]
        alloc = winner.get("Allocation")
        if isinstance(alloc, str) and alloc.strip():
            st.info(f"**{winner['Team']}** ({winner['Probability of ruin']:.1f}% probability of ruin) "
                    f"built: {alloc}")
        else:
            st.caption("No allocation recorded for the current #1 (played before this feature was added).")
