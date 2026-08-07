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

Styling is intentionally more playful than the main comparison tool (gradient hero banner, big
animated reveal card, medal leaderboard) - this page is a game, not a client-facing pitch deck -
but reuses the main app's own probability-of-ruin colour coding (green/amber/red) so the one number
that actually matters still reads the same way in both places.
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
from portfolios import AC, PORTFOLIOS, PORTFOLIO_META, DATA_DIR, EQUITY_CLASSES

st.set_page_config(page_title="Mobius Wealth - Portfolio Builder Game", layout="wide", page_icon="🎮")

# Same risk colours as the main app's probability-of-ruin cards (app.py's ruin_color logic) -
# consistent meaning across both pages, just wrapped in more decorative packaging here.
COLOR_GOOD = "#0ca30c"
COLOR_WARN = "#c98500"
COLOR_BAD = "#d03b3b"

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;800&display=swap');

    /* Page-wide theme wash + confetti dots, so the whole page reads as "a game", not just the
       hero card sitting on an otherwise plain white Streamlit page. Deliberately very low alpha
       so body text everywhere else stays fully legible in both light and dark mode. */
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(rgba(108,92,231,0.05) 2px, transparent 2px),
            linear-gradient(160deg, rgba(108,92,231,0.05), rgba(0,180,216,0.05) 45%, rgba(12,163,12,0.04) 100%);
        background-size: 34px 34px, 100% 100%;
    }
    h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
        font-family: 'Baloo 2', sans-serif !important;
    }
    /* Secondary (non-primary) buttons get the same playful pill treatment, just quieter, so
       "Refresh leaderboard" / "Build another portfolio" etc. feel like part of the same game
       instead of default grey Streamlit chrome. */
    div[data-testid="stButton"] > button:not([kind="primary"]) {
        font-family: 'Baloo 2', sans-serif;
        font-weight: 700;
        border-radius: 999px;
        border: 2px solid #6C5CE7;
        color: #6C5CE7;
        transition: transform 0.15s ease, background 0.15s ease;
    }
    div[data-testid="stButton"] > button:not([kind="primary"]):hover {
        background: rgba(108, 92, 231, 0.1);
        transform: scale(1.015);
        color: #6C5CE7;
    }
    /* Card-wrap the allocation editor and leaderboard tables so they feel like game panels
       rather than plain spreadsheet grids. */
    [data-testid="stDataFrame"] {
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 4px 14px rgba(76, 41, 196, 0.10);
        border: 1px solid rgba(108, 92, 231, 0.18);
    }
    .step-row { display: flex; gap: 0.6rem; margin-bottom: 1.2rem; }
    .step-pill {
        flex: 1; text-align: center; padding: 0.55rem 0.5rem; border-radius: 999px;
        font-family: 'Baloo 2', sans-serif; font-weight: 700; font-size: 0.85rem;
        border: 2px solid rgba(108, 92, 231, 0.25); color: rgba(108, 92, 231, 0.55);
        background: rgba(108, 92, 231, 0.04); transition: all 0.2s ease;
    }
    .step-pill.active {
        border-color: #6C5CE7; color: white;
        background: linear-gradient(90deg, #6C5CE7, #00B4D8);
        box-shadow: 0 4px 12px rgba(108, 92, 231, 0.35);
    }
    .step-pill.done { border-color: #0ca30c; color: #0ca30c; background: rgba(12,163,12,0.06); }

    .game-hero {
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, #6C5CE7 0%, #00B4D8 55%, #0ca30c 120%);
        border-radius: 18px;
        padding: 1.6rem 2rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 8px 24px rgba(76, 41, 196, 0.25);
    }
    .game-hero::before {
        content: "";
        position: absolute;
        inset: 0;
        background-image:
            radial-gradient(rgba(255,255,255,0.16) 2px, transparent 2px),
            radial-gradient(rgba(255,255,255,0.12) 2px, transparent 2px);
        background-size: 42px 42px;
        background-position: 0 0, 21px 21px;
        pointer-events: none;
    }
    .game-hero h1 {
        position: relative;
        font-family: 'Baloo 2', sans-serif;
        color: white;
        font-size: 2.1rem;
        margin: 0 0 0.35rem 0;
    }
    .game-hero h1 .wobble { display: inline-block; animation: wobble 2.4s ease-in-out infinite; }
    @keyframes wobble {
        0%, 100% { transform: rotate(0deg); }
        25% { transform: rotate(-8deg); }
        75% { transform: rotate(8deg); }
    }
    .game-hero p {
        position: relative;
        color: rgba(255,255,255,0.92);
        font-size: 0.98rem;
        margin: 0;
        max-width: 60rem;
    }
    .howto-row { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1.2rem; }
    .howto-card {
        flex: 1 1 200px;
        border-radius: 14px;
        padding: 0.9rem 1rem;
        background: rgba(108, 92, 231, 0.06);
        border: 1px solid rgba(108, 92, 231, 0.18);
    }
    .howto-card .num {
        display: inline-flex; align-items: center; justify-content: center;
        width: 1.6rem; height: 1.6rem; border-radius: 50%;
        background: linear-gradient(90deg, #6C5CE7, #00B4D8);
        color: white; font-family: 'Baloo 2', sans-serif; font-weight: 800; font-size: 0.85rem;
        margin-bottom: 0.4rem;
    }
    .howto-card .txt { font-size: 0.85rem; color: inherit; opacity: 0.9; }
    .stats-banner {
        display: flex; flex-wrap: wrap; gap: 1.5rem; justify-content: center;
        border-radius: 14px; padding: 0.75rem 1rem; margin-bottom: 1.2rem;
        background: linear-gradient(90deg, rgba(108,92,231,0.10), rgba(0,180,216,0.10));
        border: 1px solid rgba(108, 92, 231, 0.18);
        font-size: 0.9rem; font-weight: 600;
    }
    .stat-card {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 14px;
        padding: 0.85rem 1rem;
        text-align: center;
        background: rgba(128,128,128,0.06);
        transition: transform 0.15s ease;
    }
    .stat-card:hover { transform: translateY(-2px); }
    .stat-card .label {
        font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.05em; color: #898781;
    }
    .stat-card .value {
        font-size: 1.6rem; font-weight: 800; line-height: 1.3;
    }
    .stat-card .comment {
        font-size: 0.78rem; font-style: italic; opacity: 0.75; margin-top: 0.35rem;
    }
    div[data-testid="stButton"] > button[kind="primary"] {
        font-family: 'Baloo 2', sans-serif;
        font-size: 1.1rem;
        font-weight: 700;
        border-radius: 999px;
        background: linear-gradient(90deg, #6C5CE7, #00B4D8);
        border: none;
        padding: 0.7rem 0;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        transform: scale(1.015);
        box-shadow: 0 6px 18px rgba(108, 92, 231, 0.4);
    }
    @keyframes popIn {
        0% { transform: scale(0.4); opacity: 0; }
        60% { transform: scale(1.12); opacity: 1; }
        80% { transform: scale(0.96); }
        100% { transform: scale(1); }
    }
    @keyframes numberPop {
        0% { transform: scale(0.3); opacity: 0; }
        50% { transform: scale(1.25); opacity: 1; }
        75% { transform: scale(0.9); }
        100% { transform: scale(1); }
    }
    .result-card {
        border-radius: 20px;
        padding: 1.8rem 2rem;
        text-align: center;
        color: white;
        animation: popIn 0.5s cubic-bezier(.34,1.56,.64,1);
        box-shadow: 0 10px 28px rgba(0,0,0,0.18);
        margin-bottom: 1rem;
    }
    .result-card .big-number {
        font-family: 'Baloo 2', sans-serif;
        font-size: 4.6rem;
        font-weight: 800;
        line-height: 1.1;
        display: inline-block;
        animation: numberPop 0.6s 0.15s cubic-bezier(.34,1.56,.64,1) backwards;
        text-shadow: 0 4px 18px rgba(0,0,0,0.25);
    }
    .result-card .tagline {
        font-size: 1.05rem;
        opacity: 0.95;
        margin-top: 0.3rem;
    }
    .battle-card {
        border-radius: 14px;
        padding: 1rem;
        text-align: center;
        border: 2px solid rgba(128,128,128,0.2);
    }
    .battle-card.winner { border-color: #0ca30c; background: rgba(12,163,12,0.08); }
    .battle-card .name { font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.03em; color: #898781; }
    .battle-card .pct { font-size: 1.7rem; font-weight: 800; }
    .badge-row { display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: center;
        margin: 0.75rem 0 1rem 0; }
    .badge-pill {
        font-family: 'Baloo 2', sans-serif;
        font-size: 0.85rem;
        font-weight: 700;
        padding: 0.35rem 0.9rem;
        border-radius: 999px;
        background: linear-gradient(90deg, #6C5CE7, #00B4D8);
        color: white;
        box-shadow: 0 3px 10px rgba(108, 92, 231, 0.3);
    }
    .suspense-text {
        text-align: center;
        font-size: 1.1rem;
        font-weight: 600;
        color: #6C5CE7;
        padding: 1rem 0;
    }
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
    re-simulating Four Seasons/Better on every single reveal click. Returns the full SimResult
    (not just prob_ruin) so its simulated paths can feed the fan chart too."""
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
    "<div class='game-hero'><h1><span class='wobble'>🎮</span> Build Your Own Portfolio</h1>"
    "<p>Assign weightings (and fees) across asset classes, then find out how likely your portfolio "
    "is to run out of money in retirement. Runs on the exact same simulation engine and market data "
    "as the main Mobius Wealth comparison tool - nothing here is a simplified stand-in. Play on your "
    "own device - everyone's score lands on the shared leaderboard at the bottom of the page. 🏁</p>"
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

editor_key = f"game_editor_{granularity}"
if editor_key not in st.session_state:
    st.session_state[editor_key] = pd.DataFrame({
        "Asset class": labels,
        "Weight %": [0.0] * len(labels),
        "Fee % pa": [0.10] * len(labels),
    })

team_name = st.text_input("🏷️ Team / player name", key="team_name",
                           help="Shown on the leaderboard - pick something your team will recognise.")

st.markdown("#### 🏗️ Your allocation")
st.caption("Set a weight for each asset class you want to hold (they must add up to 100%), and the "
           "annual fee you're assuming for each. Leave a row at 0% to leave it out entirely.")
edited = st.data_editor(
    st.session_state[editor_key],
    key=f"editor_widget_{granularity}",
    num_rows="fixed",
    hide_index=True,
    use_container_width=True,
    column_config={
        "Asset class": st.column_config.TextColumn(disabled=True),
        "Weight %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.5, format="%.1f"),
        "Fee % pa": st.column_config.NumberColumn(min_value=0.0, max_value=3.0, step=0.01, format="%.2f"),
    },
)
st.session_state[editor_key] = edited

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
    four_seasons_result = _benchmark_result("Four Seasons", asset_df, cpi, profile)
    better_result = _benchmark_result("Better", asset_df, cpi, profile)
    four_seasons_ruin = four_seasons_result.prob_ruin
    better_ruin = better_result.prob_ruin

    st.markdown("#### ⚔️ How you compare")
    contenders = [
        ("You", prob_ruin),
        (PORTFOLIO_META.get("Four Seasons", {}).get("DisplayName", "Aspen Four Seasons"), four_seasons_ruin),
        (PORTFOLIO_META.get("Better", {}).get("DisplayName", "Mobius Better"), better_ruin),
    ]
    best_ruin = min(p for _, p in contenders)
    bcols = st.columns(3)
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
    beat_fs = prob_ruin < four_seasons_ruin
    beat_better = prob_ruin < better_ruin
    if beat_better:
        st.success("🎉 You beat Mobius Better - the tool's own most diversified construction. Impressive.")
    elif beat_fs:
        st.info("👍 You beat Aspen Four Seasons, but Mobius Better still edges you out.")
    else:
        st.info("📉 Both benchmark portfolios currently beat you - room to improve.")

    st.markdown("#### 📊 How your pot could evolve - everyone, side by side")
    st.caption("Interactive - hover for exact values, drag to zoom. The bold line is each portfolio's "
               "median (typical) simulated outcome; the shaded band is the middle 50% of simulated futures.")
    fan = go.Figure()
    fan_series = [
        ("You", COLOR_GOOD if prob_ruin < 0.15 else COLOR_WARN if prob_ruin < 0.30 else COLOR_BAD,
         st.session_state[f"game_paths_{granularity}"]),
        (PORTFOLIO_META.get("Four Seasons", {}).get("DisplayName", "Aspen Four Seasons"), "#6C5CE7",
         four_seasons_result.paths),
        (PORTFOLIO_META.get("Better", {}).get("DisplayName", "Mobius Better"), "#00B4D8",
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

    _row_colors = {0: "rgba(255,215,0,0.20)", 1: "rgba(192,192,192,0.20)", 2: "rgba(205,127,50,0.18)"}

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
