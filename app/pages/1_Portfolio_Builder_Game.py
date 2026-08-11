"""
Portfolio Builder Game - a fun, standalone activity built on the SAME simulation engine and
asset-class data as the main comparison tool (src/engine.py, data/asset_class_returns.csv), so a
player's constructed portfolio is scored on exactly the same probability-of-ruin metric the main
app uses - just with the player choosing the allocation and fees themselves, across the Mobius
fund store's own asset-class sub-categories (or, in the alternate mode, the finer individual
building blocks), instead of comparing two pre-built portfolios. After revealing, the player can
also click through real historical crises (CRASH_SCENARIOS) to re-test the SAME built portfolio
starting right as a real crash happened, instead of the full-history average - "would this have
survived the 2008 crash" as a fun, optional exploration once the headline score is already in.

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
import random
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import tax
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
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
    }}
    .howto-card:hover {{
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(14, 15, 20, 0.1);
        border-color: {CARBON_BLACK};
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

    .crash-banner {{
        border-radius: 14px; padding: 0.9rem 1.2rem; margin-bottom: 0.75rem;
        color: white; text-align: center;
        font-size: 0.95rem; font-weight: 600;
        box-shadow: 0 4px 14px rgba(14, 15, 20, 0.18);
        animation: popIn 0.4s cubic-bezier(.34,1.56,.64,1);
    }}

    .fun-fact-banner {{
        border-radius: 14px; padding: 0.75rem 1.1rem; margin-bottom: 1rem;
        background: {CLOUD_BLUE}; border: 1px solid {STEEL_GREY};
        font-size: 0.88rem; color: {CARBON_BLACK};
    }}
    .fun-fact-banner b {{ font-weight: 700; }}

    .cheat-sheet-row {{
        padding: 0.5rem 0.6rem; border-bottom: 1px solid {STEEL_GREY};
        font-size: 0.85rem; border-radius: 8px; margin: 0 -0.6rem;
        transition: background 0.15s ease;
    }}
    .cheat-sheet-row:hover {{ background: {GREY_100}; }}
    .cheat-sheet-row:last-child {{ border-bottom: none; }}
    .cheat-sheet-row .cs-head {{
        display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline;
        gap: 0.5rem; margin-bottom: 0.15rem;
    }}
    .cheat-sheet-row .cs-label {{ font-weight: 600; }}
    .cheat-sheet-row .cs-risk {{ white-space: nowrap; font-size: 0.8rem; }}
    .cheat-sheet-row .cs-blurb {{ color: {GREY_700}; }}

    .risk-dial-label {{
        display: flex; justify-content: space-between; font-size: 0.8rem;
        font-weight: 600; color: {GREY_700}; margin-bottom: 0.25rem;
    }}
    .risk-dial-track {{
        position: relative; height: 10px; border-radius: 6px; margin-bottom: 1rem;
        background: linear-gradient(90deg, {COLOR_GOOD}, {COLOR_WARN}, {COLOR_BAD});
    }}
    .risk-dial-marker {{
        position: absolute; top: -4px; width: 4px; height: 18px; border-radius: 2px;
        background: {CARBON_BLACK}; box-shadow: 0 0 0 2px white;
        transition: left 0.25s ease;
    }}

    .stat-card {{
        border: 1px solid {STEEL_GREY};
        border-radius: 14px;
        padding: 0.85rem 1rem;
        text-align: center;
        background: white;
        transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }}
    .stat-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 8px 18px rgba(14, 15, 20, 0.1);
        border-color: {CARBON_BLACK};
    }}
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

    .champion-card {{
        border-radius: 22px;
        padding: 2rem 2rem 1.7rem;
        text-align: center;
        color: white;
        background: linear-gradient(135deg, {COLOR_WARN}, #E8C860);
        animation: popIn 0.55s cubic-bezier(.34,1.56,.64,1);
        box-shadow: 0 14px 34px rgba(201,162,39,0.35);
        margin: 0.75rem 0 1.1rem;
        transition: box-shadow 0.2s ease, transform 0.2s ease;
    }}
    .champion-card:hover {{
        box-shadow: 0 18px 40px rgba(201,162,39,0.5);
        transform: translateY(-2px);
    }}
    .champion-card .trophy {{
        font-size: 2.6rem;
        animation: numberPop 0.6s 0.1s cubic-bezier(.34,1.56,.64,1) backwards;
    }}
    .champion-card .champion-name {{
        font-weight: 800;
        font-size: 2.1rem;
        line-height: 1.25;
        margin: 0.15rem 0 0.7rem;
        text-shadow: 0 4px 18px rgba(0,0,0,0.25);
    }}
    .champion-card .champion-stats {{
        display: flex; justify-content: center; gap: 1.8rem; flex-wrap: wrap;
        margin-top: 0.4rem;
    }}
    .champion-card .champion-stat-value {{
        font-size: 1.4rem; font-weight: 700;
    }}
    .champion-card .champion-stat-label {{
        font-size: 0.66rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.05em; opacity: 0.85;
    }}

    .battle-card {{
        border-radius: 14px;
        padding: 1rem;
        text-align: center;
        border: 2px solid {STEEL_GREY};
        background: white;
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }}
    .battle-card:hover {{ transform: translateY(-3px); box-shadow: 0 10px 22px rgba(14, 15, 20, 0.12); }}
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
        display: inline-block;
        cursor: help;
        transition: transform 0.15s cubic-bezier(.34,1.56,.64,1), box-shadow 0.15s ease,
            background 0.15s ease;
    }}
    .badge-pill:hover {{
        transform: scale(1.08) translateY(-1px);
        box-shadow: 0 6px 14px rgba(14, 15, 20, 0.3);
        background: {GREY_900};
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

# Native emoji rendering varies a lot by OS/browser (Windows vs Mac vs different Chrome builds
# render the same character noticeably differently) - jarring on a shared screen at a live event
# with a mix of devices. Twemoji (Twitter's open-source emoji set, MIT/CC-BY licensed) replaces
# every emoji character in the rendered page with a consistent flat-style SVG, the same on every
# device. Loaded from jsdelivr's CDN - already the pattern this page uses for the Inter Google
# Font import above, so no new class of dependency. Runs via a debounced MutationObserver rather
# than a one-off pass, since Streamlit re-renders the DOM on every widget interaction (slider
# drags, reveals, host actions) and each of those can introduce new emoji-bearing text that also
# needs converting - re-parsing already-converted content is a cheap no-op for twemoji, so the
# debounce exists purely to avoid firing dozens of times during a rapid burst of DOM changes
# (e.g. a slider drag), not to guard against incorrect behaviour.
st.markdown(
    """
    <style>
    img.twemoji-icon {
        height: 1.15em; width: 1.15em;
        margin: 0 0.05em 0.1em 0.12em;
        vertical-align: -0.2em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
# <script> tags inserted via st.markdown's unsafe_allow_html never execute - Streamlit sets them
# via innerHTML, and browsers deliberately don't run script tags inserted that way. components.html
# renders into a real iframe instead, where scripts genuinely execute; the script below reaches
# back OUT to the actual page via window.parent.document, since twemoji needs to rewrite the real
# page content, not the empty iframe it's running inside. height=0 keeps the (invisible) iframe
# from taking up any layout space.
components.html(
    """
    <script src="https://cdn.jsdelivr.net/npm/twemoji@14.0.2/dist/twemoji.min.js"
            crossorigin="anonymous"></script>
    <script>
    (function() {
        function parseNow() {
            if (window.twemoji) {
                window.twemoji.parse(window.parent.document.body, {
                    folder: "svg", ext: ".svg", className: "twemoji-icon",
                });
            }
        }
        var waitForLib = setInterval(function() {
            if (window.twemoji) {
                clearInterval(waitForLib);
                parseNow();
                var debounceTimer = null;
                var observer = new MutationObserver(function() {
                    clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(parseNow, 200);
                });
                observer.observe(window.parent.document.body, {childList: true, subtree: true});
            }
        }, 100);
    })();
    </script>
    """,
    height=0,
)

GAME_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "game_state"
GAME_STATE_DIR.mkdir(exist_ok=True)
LEADERBOARD_CSV = GAME_STATE_DIR / "leaderboard.csv"
LEADERBOARD_COLUMNS = ["Time", "Team", "Mode", "Probability of ruin",
                        "Median annual return %", "Asset classes used", "Allocation"]

# Purely cosmetic team mascot picker - prepended to the team name string (see team_display)
# rather than stored as its own column, so it needs no leaderboard schema change.
TEAM_EMOJIS = ["🦄", "🐉", "🦁", "🐙", "🚀", "🔥", "🎯", "🍀", "🌟", "🦊", "🐝", "🐺"]

SUSPENSE_MESSAGES = [
    "🎲 Testing your portfolio against 2,000 possible futures...",
    "📉 Simulating market crashes...",
    "📈 Simulating bull runs...",
    "🧮 Crunching the numbers...",
]

# Real historical crisis starting points - the same "sequence of returns" stress-test scenarios
# the main app offers (see app.py's STRESS_SCENARIOS), reused here as an optional "crash
# challenge": instead of the full 2000-2026 history, the simulation only bootstraps from months
# AFTER the chosen crisis date, so the question becomes "would this portfolio have survived if
# retirement started right as this actually happened" rather than an average over all history.
CRASH_SCENARIOS = {
    "Full history (no crash challenge)": None,
    "💻 Dot-com crash (Mar 2000)": date(2000, 3, 1),
    "🏦 Global Financial Crisis (Oct 2007)": date(2007, 10, 1),
    "📈 2022 inflation shock (Jan 2022)": date(2022, 1, 1),
}


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


@st.cache_resource(show_spinner=False)
def _host_state() -> dict:
    """One dict shared by every session on this server process (st.cache_resource returns the
    SAME object to every user, unlike st.session_state which is per-browser-tab) - lets one host
    publish a client scenario that every group's tab picks up on their next rerun, with no polling
    or extra storage needed. Relies on this being a normal single-process Streamlit Cloud
    deployment; if it's ever scaled across multiple replicas this would need to move to the same
    Google Sheets backend as the leaderboard instead."""
    return {
        "age": 65, "horizon": 30, "pot": 500_000, "spend": 20_000,
        "max_classes": 6, "max_fee_pct": 0.20,
        # Tax & State Pension - off by default (matches the main app's own default), a purely
        # optional "fun side thing" the host can switch on for a group that wants the extra
        # realism. When on, "Desired annual spend" is treated as NET (take-home), same convention
        # the main app uses - see its own "Tax & State Pension" sidebar section for the full model.
        "apply_tax": False, "sp_amount": tax.FULL_NEW_STATE_PENSION_ANNUAL,
        "sp_age": tax.DEFAULT_STATE_PENSION_AGE,
        "updated_at": None, "updated_by": None,
        "revealed": False, "revealed_at": None,
    }


def _host_pin() -> str:
    """Falls back to a default PIN if host_pin isn't set in st.secrets - fine for a low-stakes
    internal game, but set one (see README) so a random player can't lock in a joke scenario."""
    try:
        return str(st.secrets.get("host_pin", "mobius2026"))
    except Exception:
        return "mobius2026"


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


# Extra construction-style groupings for badges, at the same individual-building-block label
# level _badges() receives its `weights` in (post FUND_STORE_MAP expansion) - separate from
# EQUITY_CLASSES (imported from portfolios.py, used across the main app too) since these two
# groupings are specific to this game's flair tags, not shared model logic.
OVERSEAS_CLASSES = {
    "EM Equities", "Eq EM Net", "EM Corp Bond", "Global Bonds", "Global Agg Bonds",
    "US Treasuries 20yr+", "US HY Corp Bond", "US ABS", "US Prop REITS",
}
ALTERNATIVE_CLASSES = {
    "Commodities", "Infrastructure", "REITs", "US Prop REITS", "Securitised Credit",
    "US ABS", "Hedge Fund Credit Suisse", "HF Trend",
}


def _badges(weights, custom_fee, selected_count, max_classes):
    """Flair tags based on HOW a portfolio was built, not the score - separate from the tier
    verdict (which is purely about the outcome), these reward specific construction choices."""
    equity_weight = float(weights[weights.index.isin(EQUITY_CLASSES)].sum())
    overseas_weight = float(weights[weights.index.isin(OVERSEAS_CLASSES)].sum())
    alt_weight = float(weights[weights.index.isin(ALTERNATIVE_CLASSES)].sum())
    max_single = float(weights.max()) if len(weights) else 0.0
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
    if max_single >= 0.95:
        tags.append("🎰 All In")
    if overseas_weight >= 0.3:
        tags.append("🌍 Globe Trotter")
    if alt_weight >= 0.15:
        tags.append("💎 Alternative Investor")
    return tags


# Hover text for each badge - shown via a native tooltip on the badge pill itself, since these
# earn their keep by being read, not just collected. Keys must match _badges()'s tag strings
# exactly (emoji + label).
BADGE_MEANINGS = {
    "🎲 Risk Taker": "80%+ in equities. Bold. Reckless. Possibly both.",
    "🛡️ Ultra Safe": "20% or less in equities. Sleeps very soundly at night.",
    "⚖️ Balanced": "35-65% in equities. The have-your-cake-and-eat-it portfolio.",
    "💰 Fee Hawk": "Weighted fee under 0.15% pa. Squeezed every last basis point out of this.",
    "🌐 Diversifier": "Used every asset class the cap allowed. Didn't leave a single one on the table.",
    "🎰 All In": "95%+ in a single asset class. Full send, no plan B.",
    "🌍 Globe Trotter": "30%+ overseas exposure. Passport fully stamped.",
    "💎 Alternative Investor": "15%+ in commodities/infrastructure/property/credit alternatives. "
                                "Too cool for plain stocks and bonds.",
}


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

# Plain-English blurb + simple risk tier for every label a slider can show, across BOTH
# granularity modes (fund store categories and individual building blocks) - aimed at players
# who don't work with this stuff day to day. Shown as each slider's "?" tooltip and in the
# cheat-sheet expander. Risk tiers are a simplified, general steer for this game, not advice.
ASSET_CLASS_INFO: dict[str, tuple[str, str]] = {
    # Fund store categories
    "Commodities": ("Raw materials like oil, gold and crops. Prices swing with global "
                     "supply/demand and inflation.", "🔴 Higher risk"),
    "Corporate Bonds": ("Loans to companies that pay you interest. Riskier than government "
                         "bonds, since companies can default.", "🟡 Medium risk"),
    "Equity": ("Ownership stakes in companies (shares). Higher long-term growth potential, "
               "but bigger swings along the way.", "🔴 Higher risk"),
    "Gilts": ("UK government bonds. Seen as one of the safer UK holdings, but returns are "
              "modest.", "🟢 Lower risk"),
    "Index Linked Gilts": ("UK government bonds whose payouts rise with inflation - useful "
                            "protection when prices are climbing fast.", "🟢 Lower risk"),
    "Infrastructure": ("Investments in things like toll roads, airports and utilities - "
                        "steady, essential-service cash flows.", "🟡 Medium risk"),
    "LDI": ("Liability-Driven Investment - a strategy that matches assets to a pension's "
            "future payment obligations, rather than tracking a single index.", "🟢 Lower risk"),
    "Money Markets": ("Cash and short-term deposits. The safest, most stable option, but the "
                       "lowest long-term growth.", "🟢 Lower risk"),
    "Multi Asset": ("A ready-blended mix of several asset classes in one fund, aiming for "
                     "diversification in a single holding.", "🟡 Medium risk"),
    "Multi Asset Credit": ("A blended mix of different types of corporate/credit debt, aiming "
                            "to diversify credit risk in one fund.", "🟡 Medium risk"),
    "Overseas Government Bonds": ("Bonds issued by governments outside the UK - adds "
                                   "geographic spread to the 'safe' part of a portfolio.", "🟢 Lower risk"),
    "Private Credit": ("Loans to companies made outside the public bond market, often with "
                        "higher yields in exchange for being harder to sell quickly.", "🟡 Medium risk"),
    "Private Equity": ("Ownership stakes in companies not listed on a public stock exchange - "
                        "high potential returns, but hard to sell quickly.", "🔴 Higher risk"),
    "Private Markets Multi Asset": ("A blended mix of several private (non-listed) asset "
                                     "classes in one fund.", "🔴 Higher risk"),
    "Property": ("Real estate, often via listed property companies - a mix of rental income "
                 "and price growth.", "🟡 Medium risk"),
    "Real Assets": ("Physical assets like land, resources and infrastructure - tend to hold "
                     "value relatively well against inflation.", "🟡 Medium risk"),
    "Securitised Credit": ("Bundles of loans (like mortgages) packaged into tradeable "
                            "securities - extra yield in exchange for extra complexity.", "🟡 Medium risk"),
    # Individual building blocks
    "Global Equities": ("Shares in large companies across developed markets worldwide.", "🔴 Higher risk"),
    "EM Equities": ("Shares in companies from emerging economies (e.g. China, India, Brazil) - "
                     "higher growth potential, higher volatility.", "🔴 Higher risk"),
    "Global Bonds": ("A broad mix of government and corporate bonds from around the world.", "🟡 Medium risk"),
    "UK Gilts All Stocks": ("The full range of UK government bonds, short and long-dated "
                             "combined.", "🟢 Lower risk"),
    "UK Gilts 15yr+": ("Long-dated UK government bonds - more sensitive to interest rate "
                        "changes than short-dated gilts.", "🟡 Medium risk"),
    "UK Index-Linked Gilts": ("UK government bonds that rise with inflation.", "🟢 Lower risk"),
    "REITs": ("Real Estate Investment Trusts - listed companies that own and manage property, "
              "paying out rental income.", "🟡 Medium risk"),
    "Cash": ("Bank deposits and equivalents - the safest holding, but returns rarely beat "
             "inflation over time.", "🟢 Lower risk"),
    "UK Gilts <5yr": ("Short-dated UK government bonds - lower interest-rate risk than longer "
                       "gilts.", "🟢 Lower risk"),
    "US Treasuries 20yr+": ("Long-dated US government bonds - a very safe issuer, but "
                             "sensitive to interest rate moves.", "🟡 Medium risk"),
    "Global Agg Bonds": ("A broad global mix of investment-grade government and corporate "
                          "bonds.", "🟡 Medium risk"),
    "Eq Gbl DM Quality Gross": ("Developed-market shares in financially strong 'quality' "
                                 "companies - a steadier equity style.", "🟡 Medium risk"),
    "Eq Gbl DM Novum Mgd Vol": ("Developed-market shares managed specifically to reduce "
                                 "volatility.", "🟡 Medium risk"),
    "Eq EM Net": ("Emerging market shares, net of fees - similar to EM Equities.", "🔴 Higher risk"),
    "US HY Corp Bond": ("US 'high yield' corporate bonds - higher interest income for taking "
                         "on more default risk.", "🔴 Higher risk"),
    "US ABS": ("US Asset-Backed Securities - bonds backed by pools of loans like auto or "
               "credit card debt.", "🟡 Medium risk"),
    "EM Corp Bond": ("Corporate bonds issued by companies in emerging markets - higher yield, "
                      "higher risk.", "🔴 Higher risk"),
    "US Prop REITS": ("US-listed Real Estate Investment Trusts.", "🟡 Medium risk"),
    "Commod": ("Commodities (legacy label) - raw materials like oil, gold and crops.", "🔴 Higher risk"),
    "Hedge Fund Credit Suisse": ("A hedge fund strategy index - aims for returns less tied to "
                                  "normal market ups and downs.", "🟡 Medium risk"),
    "HF Trend": ("A 'trend following' hedge fund strategy - aims to profit from sustained "
                 "price trends in either direction.", "🟡 Medium risk"),
    "Eq Gbl DM Value Gross": ("Developed-market shares in 'value' companies - stocks that look "
                               "cheap relative to fundamentals.", "🔴 Higher risk"),
    "Eq Gbl DM Min vol Gross": ("Developed-market shares specifically selected to minimise "
                                 "volatility.", "🟡 Medium risk"),
}


def _asset_help(label: str) -> str | None:
    info = ASSET_CLASS_INFO.get(label)
    return f"{info[1]} — {info[0]}" if info else None


_RISK_TIER_SCORE = {"🟢": 1.0, "🟡": 2.0, "🔴": 3.0}


def _live_risk_read(edited_df) -> tuple[float, str, str] | None:
    """A cheap, instant proxy for how risky the CURRENT slider allocation looks, built from each
    label's ASSET_CLASS_INFO risk tier weighted by its allocation - not the real simulation (that
    only runs on submit), just live feedback while building so the sliders feel like they matter
    immediately. Returns (0-1 dial position, tier label, tier color) or None if nothing's allocated."""
    total = float(edited_df["Weight %"].sum())
    if total <= 0:
        return None
    weighted = 0.0
    for _, r in edited_df.iterrows():
        if r["Weight %"] <= 0:
            continue
        info = ASSET_CLASS_INFO.get(r["Asset class"])
        tier_score = _RISK_TIER_SCORE.get(info[1][0], 2.0) if info else 2.0
        weighted += r["Weight %"] * tier_score
    score = weighted / total  # 1.0 (all lower-risk) .. 3.0 (all higher-risk)
    position = (score - 1.0) / 2.0  # 0.0 .. 1.0 for the dial marker
    if score < 1.6:
        return position, "🟢 Lower-risk mix", COLOR_GOOD
    elif score < 2.4:
        return position, "🟡 Balanced mix", COLOR_WARN
    else:
        return position, "🔴 Higher-risk mix", COLOR_BAD


# General, well-established investing/market-history facts - deliberately kept to safe,
# verifiable territory rather than obscure figures. One is shown at random per build session
# (not re-rolled on every slider tweak) as light "did you know" colour while building.
FUN_FACTS = [
    "A UK 60/40 stocks/bonds portfolio has historically had noticeably smaller drawdowns than "
    "an all-equity portfolio — the classic diversification trade-off.",
    "The dot-com crash (2000-2003) wiped out roughly half the value of global tech-heavy "
    "indices before markets eventually recovered.",
    "In the 2008 Global Financial Crisis, global equities fell by around half, peak to trough.",
    "Cash feels 'safe', but holding too much for too long is its own risk — inflation quietly "
    "erodes its real value over time.",
    "Spreading money across asset classes that don't move in lockstep is often called the only "
    "'free lunch' in investing: it can lower risk without necessarily lowering expected return.",
    "Government bonds are generally considered safer than shares, but they're not risk-free — "
    "their prices fall when interest rates rise.",
    "'Sequence of returns' risk means WHEN you hit a market crash in retirement can matter more "
    "than the average return over your whole retirement.",
    "Private equity and private credit often look smoother than public markets — but that's "
    "partly because they're valued less often, not because they're actually less volatile.",
]

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

# Shared reveal gate: the host controls a single "revealed" flag on the same singleton used for
# the shared scenario (_host_state()), so submitting a portfolio computes and stores the score
# right away but nobody sees probability of ruin, crash tests, or the leaderboard's numbers until
# the host reveals - at which point everyone's own already-computed result unlocks on their next
# rerun. just_revealed is True for exactly one script run per session (the first rerun after the
# flag flips), so the drumroll/balloons moment plays once instead of on every later interaction.
host_state = _host_state()
revealed = host_state.get("revealed", False)
just_revealed = revealed and not st.session_state.get("_seen_reveal", False)
st.session_state["_seen_reveal"] = revealed

_lb_for_banner = _load_leaderboard()
if _lb_for_banner.empty:
    st.markdown(
        "<div class='stats-banner'>🌱 No portfolios built yet - be the first!</div>",
        unsafe_allow_html=True,
    )
elif not revealed:
    _n_plays = len(_lb_for_banner)
    _n_teams = _lb_for_banner["Team"].nunique()
    st.markdown(
        "<div class='stats-banner'>"
        f"<span>🎲 {_n_plays} portfolio{'s' if _n_plays != 1 else ''} submitted</span>"
        f"<span>{_n_teams} team{'s' if _n_teams != 1 else ''} playing</span>"
        "<span>🤫 Scores are hidden until the host reveals the winner</span>"
        "</div>",
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
        f"<span>{_n_teams} team{'s' if _n_teams != 1 else ''} playing</span>"
        f"<span>📊 avg probability of ruin: {_avg_ruin:.1f}%</span>"
        f"<span>🏆 best so far: {_best_row['Team']} ({_best_row['Probability of ruin']:.1f}%)</span>"
        "</div>",
        unsafe_allow_html=True,
    )

with st.expander("⚙️ Game setup (host controls)", expanded=False):
    is_host = st.session_state.get("is_host", False)

    if not is_host:
        pin_entry = st.text_input(
            "Host PIN", type="password", key="host_pin_input",
            help="Only the person running the session needs this - everyone else can skip it "
                 "and just see the scenario below.",
        )
        if pin_entry:
            if pin_entry == _host_pin():
                st.session_state["is_host"] = True
                st.rerun()
            else:
                st.error("Wrong PIN.")

    if is_host:
        st.success("✅ Host mode - Publish below applies to every group's game immediately.")
        host_name = st.text_input("Your name (shown to groups)",
                                   value=host_state["updated_by"] or "Host", key="host_name_input")
        c1, c2 = st.columns(2)
        with c1:
            _h_age = st.number_input("Starting age", 40, 90, host_state["age"], key="host_age_in")
            _h_horizon = st.slider("Time horizon (years)", 5, 40, host_state["horizon"], key="host_horizon_in")
            _h_max_classes = st.number_input(
                "Max asset classes a player can use", 1, 26, host_state["max_classes"], key="host_maxcls_in",
                help="Forces harder trade-offs instead of just spreading weight across everything on offer.",
            )
        with c2:
            _h_pot = st.number_input("Starting pot (£)", 10_000, 10_000_000, host_state["pot"],
                                      step=10_000, key="host_pot_in")
            _h_spend = st.number_input("Desired annual spend (£)", 1_000, 500_000, host_state["spend"],
                                        step=1_000, key="host_spend_in")
            _h_max_fee = st.number_input(
                "Max weighted fee allowed (% pa)", 0.0, 3.0, host_state["max_fee_pct"],
                step=0.01, key="host_maxfee_in",
                help="A second constraint alongside the asset-class cap - forces a genuine cost-vs-"
                     "diversification trade-off instead of just picking the priciest option everywhere.",
            )
        st.divider()
        st.markdown("**🧾 Tax & State Pension** *(optional fun side thing)*")
        _h_apply_tax = st.checkbox(
            "Include income tax + State Pension", value=host_state["apply_tax"], key="host_tax_in",
            help="When on, 'Desired annual spend' is treated as the NET (take-home) amount a "
                 "player wants - the model works out what actually has to come out of the pot "
                 "(gross, taxable) to deliver that, and adds the State Pension as a second income "
                 "stream once it starts. Same convention as the main comparison tool's own Tax & "
                 "State Pension setting. Off by default, since it adds a layer most groups won't "
                 "need for a quick game - switch it on for a group that wants the extra realism.",
        )
        if _h_apply_tax:
            _tc1, _tc2 = st.columns(2)
            with _tc1:
                _h_sp_amount = st.number_input(
                    "Full State Pension, today's £ per year", 0, 50_000,
                    int(round(host_state["sp_amount"])), step=100, key="host_sp_amount_in",
                )
            with _tc2:
                _h_sp_age = st.number_input(
                    "State Pension age", 55, 75, host_state["sp_age"], key="host_sp_age_in",
                )
        else:
            _h_sp_amount, _h_sp_age = host_state["sp_amount"], host_state["sp_age"]

        if st.button("📡 Publish to all groups", type="primary", use_container_width=True):
            host_state.update(
                age=_h_age, horizon=_h_horizon, pot=_h_pot, spend=_h_spend,
                max_classes=_h_max_classes, max_fee_pct=_h_max_fee,
                apply_tax=_h_apply_tax, sp_amount=_h_sp_amount, sp_age=_h_sp_age,
                updated_at=datetime.now().strftime("%H:%M:%S"),
                updated_by=host_name.strip() or "Host",
            )
            st.toast("Published - every group picks this up on their next click.", icon="📡")

        st.divider()
        st.caption(f"Leaderboard storage: {_leaderboard_mode()}")
        st.caption(f"Leaderboard has {len(_load_leaderboard())} entries.")
        if st.button("🗑️ Clear leaderboard (start a new game)"):
            _clear_leaderboard()
            host_state["revealed"] = False
            host_state["revealed_at"] = None
            st.rerun()
        if st.button("Log out of host mode"):
            st.session_state["is_host"] = False
            st.rerun()
        st.divider()

    if host_state["updated_at"]:
        st.caption(f"📡 Scenario published by **{host_state['updated_by']}** at "
                   f"{host_state['updated_at']} - every group is playing this.")
    else:
        st.caption("📡 No host scenario published yet - everyone's using the defaults below "
                    "until the host publishes one.")
    _s1, _s2, _s3, _s4, _s5, _s6 = st.columns(6)
    _s1.metric("Age", host_state["age"])
    _s2.metric("Horizon", f"{host_state['horizon']}y")
    _s3.metric("Pot", f"£{host_state['pot']:,.0f}")
    _s4.metric("Spend", f"£{host_state['spend']:,.0f}")
    _s5.metric("Max classes", host_state["max_classes"])
    _s6.metric("Max fee", f"{host_state['max_fee_pct']:.2f}%")
    if host_state["apply_tax"]:
        st.caption(f"🧾 Tax & State Pension: **on** (£{host_state['sp_amount']:,.0f}/yr from age "
                   f"{host_state['sp_age']}) - spend above is treated as NET/take-home.")
    else:
        st.caption("🧾 Tax & State Pension: off - spend above is a single pre-tax number.")

    age = host_state["age"]
    horizon = host_state["horizon"]
    pot = host_state["pot"]
    spend = host_state["spend"]
    max_classes = host_state["max_classes"]
    max_fee_pct = host_state["max_fee_pct"]
    apply_tax = host_state["apply_tax"]
    sp_amount = host_state["sp_amount"]
    sp_age = host_state["sp_age"]

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

if st.session_state.get(result_key) is None:
    _current_step = "build"
elif not revealed:
    _current_step = "waiting"
else:
    _current_step = "revealed"
st.markdown(
    "<div class='step-row'>"
    f"<div class='step-pill{' active' if _current_step == 'build' else ' done'}'>🏗️ Build</div>"
    f"<div class='step-pill{' active' if _current_step == 'waiting' else ' done' if _current_step == 'revealed' else ''}'>"
    "🤐 Submitted</div>"
    f"<div class='step-pill{' active' if _current_step == 'revealed' else ''}'>🏆 Revealed</div>"
    "</div>",
    unsafe_allow_html=True,
)

_name_col, _emoji_col = st.columns([4, 1])
with _name_col:
    team_name = st.text_input("🏷️ Team / player name", key="team_name",
                               help="Shown on the leaderboard - pick something your team will recognise.")
with _emoji_col:
    team_emoji = st.selectbox("Mascot", TEAM_EMOJIS, key="team_emoji", label_visibility="collapsed")
# The emoji is purely cosmetic flair prepended to the display name - stored as part of the same
# "Team" string everywhere (leaderboard, champion card) rather than a new column, so it works
# with the existing Google Sheets/CSV schema with no migration needed.
team_display = f"{team_emoji} {team_name.strip()}" if team_name.strip() else ""

st.markdown("#### 🏗️ Your allocation")
st.caption("Drag a slider for each asset class you want to hold (they must add up to 100%), and set "
           "the annual fee you're assuming for each. Leave a slider at 0% to leave it out entirely. "
           "New to this? Hover the **?** next to any slider for a plain-English explainer, or check "
           "the cheat sheet below.")

if "game_fun_fact" not in st.session_state:
    st.session_state["game_fun_fact"] = random.choice(FUN_FACTS)
st.markdown(
    f"<div class='fun-fact-banner'>💡 <b>Did you know?</b> {st.session_state['game_fun_fact']}</div>",
    unsafe_allow_html=True,
)

with st.expander("📚 New here? Quick asset class cheat sheet"):
    st.caption("What each asset class actually is, and roughly how risky it tends to be - "
               "a simplified steer for this game, not investment advice.")
    for _cs_label in labels:
        _cs_info = ASSET_CLASS_INFO.get(_cs_label)
        if _cs_info:
            _cs_blurb, _cs_risk = _cs_info
            st.markdown(
                "<div class='cheat-sheet-row'>"
                f"<div class='cs-head'><span class='cs-label'>{_cs_label}</span>"
                f"<span class='cs-risk'>{_cs_risk}</span></div>"
                f"<div class='cs-blurb'>{_cs_blurb}</div>"
                "</div>",
                unsafe_allow_html=True,
            )

weight_values, fee_values = [], []
header_l, header_w, header_f = st.columns([2.5, 5.5, 1.5])
with header_w:
    st.caption("WEIGHT %")
with header_f:
    st.caption("FEE % PA")
for label in labels:
    row_l, row_w, row_f = st.columns([2.5, 5.5, 1.5])
    with row_l:
        # st.slider's own help="" tooltip icon gets display:none'd along with the label when
        # label_visibility="collapsed" (verified in devtools - it's not just visually subtle,
        # it's fully hidden), so the hint is rendered here instead as a plain HTML title
        # attribute on a small info glyph next to the row's own label.
        _hint = _asset_help(label)
        _hint_html = (f" <span style='opacity:0.5; cursor:help;' title='{html.escape(_hint)}'>ⓘ</span>"
                      if _hint else "")
        st.markdown(f"<div style='padding-top:0.6rem;'>{label}{_hint_html}</div>", unsafe_allow_html=True)
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

_risk_read = _live_risk_read(edited)
if _risk_read is not None:
    _risk_pos, _risk_label, _risk_color = _risk_read
    st.markdown(
        f"<div class='risk-dial-label'><span>🎯 Live risk read</span>"
        f"<span style='color:{_risk_color};'>{_risk_label}</span></div>"
        f"<div class='risk-dial-track'>"
        f"<div class='risk-dial-marker' style='left:calc({_risk_pos * 100:.1f}% - 2px);'></div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption("A quick read on your mix as you build - not the real simulation, which only runs "
               "once you lock in your portfolio.")

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
    _stat_card("Team name", html.escape(team_display) if name_ok else "Not set yet",
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

reveal = st.button("🔒 Lock in my portfolio", type="primary",
                    disabled=not can_reveal, use_container_width=True,
                    help="Scores your portfolio and puts it on the leaderboard, but your probability "
                         "of ruin stays hidden until the host reveals the winner.")

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
                             initial_annual_spend=float(spend), apply_tax=apply_tax,
                             state_pension_annual=float(sp_amount), state_pension_age=int(sp_age))
    result = run_simulation("Your portfolio", asset_df, cpi, profile, method="stationary_block",
                             n_sims=2000, seed=42, custom_weights=weights, custom_fee=custom_fee)
    suspense_slot.empty()

    median_return = _median_cagr(result.paths, float(pot), horizon)
    st.session_state[result_key] = result.prob_ruin
    st.session_state[f"game_return_{granularity}"] = median_return
    st.session_state[f"game_fee_{granularity}"] = custom_fee
    st.session_state[f"game_paths_{granularity}"] = result.paths
    st.session_state[f"game_weights_{granularity}"] = weights
    st.session_state[f"game_badges_{granularity}"] = _badges(weights, custom_fee, selected_count, max_classes)
    _append_leaderboard({
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Team": team_display,
        "Mode": granularity,
        "Probability of ruin": round(result.prob_ruin * 100, 2),
        "Median annual return %": round(median_return * 100, 2),
        "Asset classes used": selected_count,
        "Allocation": allocation_str,
    })

# Reveal order, per explicit feedback: the shared moment (who won, how everyone stacks up) comes
# FIRST for everyone the instant it's revealed, and each player's own deep-dive stats/charts come
# LAST, as optional extras to explore once the headline result has landed - not interleaved with
# it. Previously each player's own result card appeared before they'd even seen who won, which
# read as confusing (a personal number with no context for whether it was good or bad relative to
# the room).
has_result = st.session_state.get(result_key) is not None

if has_result and not revealed:
    st.divider()
    st.markdown(
        "<div class='result-card' style='background:linear-gradient(135deg, "
        f"{GREY_900}, {CARBON_BLACK});'>"
        "<div style='font-size:1.3rem; font-weight:700;'>🤐 Portfolio locked in!</div>"
        "<div class='tagline'>Your probability of ruin is hidden until the host reveals the "
        "winner for everyone - sit tight...</div></div>",
        unsafe_allow_html=True,
    )
    _wcol1, _wcol2 = st.columns(2)
    with _wcol1:
        if st.button("🔁 Change my portfolio before reveal", use_container_width=True):
            del st.session_state[result_key]
            st.rerun()
    with _wcol2:
        if st.button("🔄 Check if it's been revealed", use_container_width=True):
            st.rerun()

st.divider()
st.markdown("### 🏆 Leaderboard")
st.caption(_leaderboard_mode())
leaderboard = _load_leaderboard()
if st.button("🔄 Refresh leaderboard"):
    st.rerun()

if is_host:
    st.markdown("---")
    if not revealed:
        if st.button("🎉 Reveal the winner to everyone", type="primary", use_container_width=True,
                      disabled=leaderboard.empty,
                      help="Unlocks every group's probability of ruin, crash tests, and this "
                           "leaderboard's numbers at once." if not leaderboard.empty else
                           "Nobody has submitted a portfolio yet."):
            host_state["revealed"] = True
            host_state["revealed_at"] = datetime.now().strftime("%H:%M:%S")
            st.rerun()
    else:
        st.success(f"✅ Revealed at {host_state.get('revealed_at') or ''} - everyone can see their score.")
        if st.button("🔒 Hide scores again (for a new round)", use_container_width=True):
            host_state["revealed"] = False
            host_state["revealed_at"] = None
            st.rerun()
    st.markdown("---")

if leaderboard.empty:
    st.caption("No scores yet - be the first to build a portfolio.")
elif not revealed:
    st.info(f"🤫 {len(leaderboard)} portfolio{'s' if len(leaderboard) != 1 else ''} submitted so far - "
            "scores stay hidden until the host reveals the winner." +
            ("" if is_host else " Ask your host when that'll be!"))
else:
    if just_revealed:
        _crown_slot = st.empty()
        for _msg in ["🥁 Drumroll please...", "🔍 Pulling up the #1 portfolio...", "👑 Crowning the champion..."]:
            _crown_slot.markdown(f"<div class='suspense-text'>{_msg}</div>", unsafe_allow_html=True)
            time.sleep(0.4)
        _crown_slot.empty()
        st.balloons()

    ranked = leaderboard.sort_values("Probability of ruin").reset_index(drop=True)
    medals = ["🥇", "🥈", "🥉"]
    ranked.insert(0, "Rank", [medals[i] if i < 3 else str(i + 1) for i in range(len(ranked))])
    current = team_display.strip().lower()
    if current:
        ranked["Team"] = ranked["Team"].apply(lambda t: f"👉 {t}" if t.strip().lower() == current else t)
    winner = ranked.iloc[0]

    # The winner pops up FIRST - the shared "who won" moment - before the full comparison table.
    alloc = winner.get("Allocation")
    # Allocation strings are built at reveal time as "Label NN%, Label NN%, ..." (see
    # allocation_str above) - parse them back into (label, weight) pairs for the champion
    # card's chart rather than showing the raw comma-separated text.
    pairs = re.findall(r"([^,]+?)\s+(\d+(?:\.\d+)?)%", alloc) if isinstance(alloc, str) and alloc.strip() else []

    st.markdown(
        f"<div class='champion-card'>"
        f"<div class='trophy'>🏆</div>"
        f"<div style='font-size:0.8rem; font-weight:700; text-transform:uppercase; "
        f"letter-spacing:0.08em; opacity:0.9;'>Champion portfolio</div>"
        f"<div class='champion-name'>{html.escape(str(winner['Team']))}</div>"
        f"<div class='champion-stats'>"
        f"<div><div class='champion-stat-value'>{winner['Probability of ruin']:.1f}%</div>"
        f"<div class='champion-stat-label'>Probability of ruin</div></div>"
        f"<div><div class='champion-stat-value'>{winner['Median annual return %']:.1f}%</div>"
        f"<div class='champion-stat-label'>Median annual return</div></div>"
        f"<div><div class='champion-stat-value'>{int(winner['Asset classes used'])}</div>"
        f"<div class='champion-stat-label'>Asset classes used</div></div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    if pairs:
        pairs_sorted = sorted(pairs, key=lambda p: -float(p[1]))
        champ_labels = [p[0].strip() for p in pairs_sorted]
        champ_values = [float(p[1]) for p in pairs_sorted]
        champ_fig = go.Figure(go.Bar(
            x=champ_values, y=champ_labels, orientation="h", marker_color=COLOR_WARN,
            text=[f"{v:.0f}%" for v in champ_values], textposition="outside",
        ))
        champ_fig.update_layout(
            height=max(220, 60 + 34 * len(champ_labels)),
            margin=dict(l=10, r=30, t=10, b=10),
            xaxis_title="Weight (%)", xaxis_range=[0, max(champ_values) * 1.2],
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(champ_fig, use_container_width=True)
    else:
        st.caption("No allocation recorded for the current #1 (played before this feature was added).")

    # Then the comparison to everyone else: how close it was, and the full ranked table.
    # "How close was it?" - compares the winner against the nearest DIFFERENT team, not just the
    # next row (which could be the same team's own second attempt if they played twice), so the
    # callout is always a genuine rivalry rather than someone racing themselves.
    _rival_rows = ranked[ranked["Team"] != winner["Team"]]
    if not _rival_rows.empty:
        _rival = _rival_rows.iloc[0]
        _gap = float(_rival["Probability of ruin"]) - float(winner["Probability of ruin"])
        if 0 <= _gap < 2.0:
            st.markdown(
                f"<div class='fun-fact-banner' style='background:{PALE_PINK}; text-align:center; "
                f"font-weight:600;'>🔥 Nail-biter! {html.escape(str(winner['Team']))} edged out "
                f"{html.escape(str(_rival['Team']))} by just {_gap:.1f} percentage points of "
                "probability of ruin.</div>",
                unsafe_allow_html=True,
            )

    # Podium tints derived from the brand palette rather than generic gold/silver/bronze web
    # colours: deepened Pale Yellow for 1st, Steel Grey for 2nd (already named "Steel" - a neat
    # fit for silver), deepened Pale Pink for 3rd.
    _row_colors = {0: "rgba(201,162,39,0.20)", 1: "rgba(204,204,213,0.35)", 2: "rgba(217,143,163,0.20)"}

    def _highlight_podium(row):
        style = f"background-color: {_row_colors[row.name]}" if row.name in _row_colors else ""
        return [style] * len(row)

    display_df = ranked.drop(columns=["Allocation"], errors="ignore")
    st.dataframe(display_df.style.apply(_highlight_podium, axis=1), hide_index=True, use_container_width=True)

# Everyone's shared moment (champion + leaderboard) has now landed above - each player's own
# deep-dive stats/charts come last, as optional extras to play with once the headline result is
# already known, rather than competing with it for attention.
if has_result and revealed:
    if just_revealed:
        _reveal_slot = st.empty()
        for _msg in ["🥁 The host has revealed the winner...", "🔓 Unlocking your result...",
                     "✨ Here it comes..."]:
            _reveal_slot.markdown(f"<div class='suspense-text'>{_msg}</div>", unsafe_allow_html=True)
            time.sleep(0.4)
        _reveal_slot.empty()

    prob_ruin = st.session_state[result_key]
    st.divider()
    st.markdown("### 🔎 Your result, in detail")
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

    st.markdown("#### 💥 Would your portfolio have survived...?")
    st.caption("Click a real historical crisis to re-test the SAME portfolio you just built, "
               "starting right as it happened - the real sequence of what actually came next, "
               "not a random resample of history.")
    _crash_profile = ClientProfile(starting_age=age, horizon_years=horizon, starting_pot=float(pot),
                                    initial_annual_spend=float(spend), apply_tax=apply_tax,
                                    state_pension_annual=float(sp_amount), state_pension_age=int(sp_age))
    _you_weights = st.session_state[f"game_weights_{granularity}"]
    _you_fee = st.session_state.get(f"game_fee_{granularity}", 0.001)
    _crash_only = {k: v for k, v in CRASH_SCENARIOS.items() if v is not None}
    _crash_cols = st.columns(len(_crash_only))
    for _col, (_label, _start_date) in zip(_crash_cols, _crash_only.items()):
        with _col:
            if st.button(_label, key=f"crash_btn_{granularity}_{_label}", use_container_width=True):
                _crash_asset_df = asset_df[asset_df.index.date >= _start_date]
                _crash_result = run_simulation(
                    "Your portfolio", _crash_asset_df, cpi, _crash_profile, method="stationary_block",
                    n_sims=2000, seed=42, custom_weights=_you_weights, custom_fee=_you_fee,
                )
                st.session_state[f"crash_result_{granularity}_{_label}"] = _crash_result.prob_ruin
                st.session_state[f"crash_paths_{granularity}_{_label}"] = _crash_result.paths
                # Better's own crash-filtered run for the same growth chart - deliberately NOT
                # going through the cached _benchmark_result() here, since its cache key
                # excludes asset_df (see its docstring) and would silently keep returning the
                # full-history result for every crash scenario if reused here - a bug already
                # hit and fixed once before for this exact function. A plain uncached call,
                # stashed in session_state per (mode, crash label), sidesteps that entirely.
                _crash_better_result = run_simulation(
                    "Better", _crash_asset_df, cpi, _crash_profile, method="stationary_block",
                    n_sims=2000, seed=42,
                )
                st.session_state[f"crash_better_paths_{granularity}_{_label}"] = _crash_better_result.paths

    for _label in _crash_only:
        _crash_key = f"crash_result_{granularity}_{_label}"
        if st.session_state.get(_crash_key) is not None:
            _crash_ruin = st.session_state[_crash_key]
            _survived = _crash_ruin < 0.5
            _verdict = "✅ SURVIVED" if _survived else "💀 WIPED OUT"
            _verdict_color = COLOR_GOOD if _survived else COLOR_BAD
            st.markdown(
                f"<div class='crash-banner' style='background:{_verdict_color};'>"
                f"{_label}: <b>{_verdict}</b> — {_crash_ruin * 100:.1f}% probability of ruin"
                "</div>",
                unsafe_allow_html=True,
            )
            _crash_paths = st.session_state.get(f"crash_paths_{granularity}_{_label}")
            _crash_better_paths = st.session_state.get(f"crash_better_paths_{granularity}_{_label}")
            if _crash_paths is not None:
                _crash_years_axis = np.arange(horizon + 1)
                _crash_series = [("You", _verdict_color, _crash_paths)]
                if _crash_better_paths is not None:
                    _crash_series.append((
                        PORTFOLIO_META.get("Better", {}).get("DisplayName", "Mobius Better"),
                        "#5B8FA8", _crash_better_paths,
                    ))
                _crash_fig = go.Figure()
                for _cs_label, _cs_color, _cs_paths in _crash_series:
                    _cq25, _cq50, _cq75 = (np.percentile(_cs_paths, q, axis=0) for q in (25, 50, 75))
                    _crash_fig.add_trace(go.Scatter(x=_crash_years_axis, y=_cq75, line=dict(width=0),
                                                     showlegend=False, hoverinfo="skip"))
                    _crash_fig.add_trace(go.Scatter(x=_crash_years_axis, y=_cq25, fill="tonexty",
                                                     line=dict(width=0), showlegend=False, hoverinfo="skip",
                                                     fillcolor=_hex_to_rgba(_cs_color, 0.18)))
                    _crash_fig.add_trace(go.Scatter(x=_crash_years_axis, y=_cq50, mode="lines",
                                                     name=_cs_label, line=dict(width=3, color=_cs_color)))
                _crash_fig.update_layout(
                    height=280, margin=dict(l=10, r=10, t=25, b=10), hovermode="x unified",
                    xaxis_title="Year", yaxis_title="Portfolio value (£)",
                    legend=dict(orientation="h", y=-0.25),
                )
                st.caption(f"How your pot could have evolved starting right as {_label} happened.")
                st.plotly_chart(_crash_fig, use_container_width=True,
                                 key=f"crash_chart_{granularity}_{_label}")

    median_return = st.session_state.get(f"game_return_{granularity}", 0.0)
    median_outcome = float(np.median(st.session_state[f"game_paths_{granularity}"][:, -1]))
    return_col1, return_col2 = st.columns(2)
    with return_col1:
        _stat_card("Median annual return", f"{median_return * 100:+.1f}%",
                   COLOR_GOOD if median_return >= 0 else COLOR_BAD, icon="📈",
                   comment=_return_comment(median_return))
    with return_col2:
        _stat_card("Legacy left behind", f"£{median_outcome:,.0f}", icon="🏺",
                   comment=_outcome_comment(median_outcome, float(pot)))

    badges = st.session_state.get(f"game_badges_{granularity}", [])
    if badges:
        st.markdown(
            "<div class='badge-row'>" + "".join(
                f"<span class='badge-pill' title='{html.escape(BADGE_MEANINGS.get(b, ''))}'>{b}</span>"
                for b in badges
            ) + "</div>",
            unsafe_allow_html=True,
        )

    profile = ClientProfile(starting_age=age, horizon_years=horizon, starting_pot=float(pot),
                             initial_annual_spend=float(spend), apply_tax=apply_tax,
                             state_pension_annual=float(sp_amount), state_pension_age=int(sp_age))
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
