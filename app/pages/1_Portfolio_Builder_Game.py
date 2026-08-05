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
app URL. The leaderboard is therefore persisted to a small CSV on disk (game_state/leaderboard.csv,
gitignored - it's session runtime state, not source data) rather than st.session_state, which is
per-browser-tab and would leave every other team's screen blank. This is a lightweight, good-enough
store for a live event with a handful of teams - not built to survive concurrent writes at scale.

Styling is intentionally more playful than the main comparison tool (gradient hero banner, big
animated reveal card, medal leaderboard) - this page is a game, not a client-facing pitch deck -
but reuses the main app's own probability-of-ruin colour coding (green/amber/red) so the one number
that actually matters still reads the same way in both places.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import pandas as pd
import streamlit as st

from engine import load_asset_returns, load_cpi, run_simulation, ClientProfile
from portfolios import AC, PORTFOLIOS, PORTFOLIO_META, DATA_DIR

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

    .game-hero {
        background: linear-gradient(135deg, #6C5CE7 0%, #00B4D8 55%, #0ca30c 120%);
        border-radius: 18px;
        padding: 1.6rem 2rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 8px 24px rgba(76, 41, 196, 0.25);
    }
    .game-hero h1 {
        font-family: 'Baloo 2', sans-serif;
        color: white;
        font-size: 2.1rem;
        margin: 0 0 0.35rem 0;
    }
    .game-hero p {
        color: rgba(255,255,255,0.92);
        font-size: 0.98rem;
        margin: 0;
        max-width: 60rem;
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
        0% { transform: scale(0.85); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
    }
    .result-card {
        border-radius: 20px;
        padding: 1.8rem 2rem;
        text-align: center;
        color: white;
        animation: popIn 0.35s ease-out;
        box-shadow: 0 10px 28px rgba(0,0,0,0.18);
        margin-bottom: 1rem;
    }
    .result-card .big-number {
        font-family: 'Baloo 2', sans-serif;
        font-size: 3.4rem;
        font-weight: 800;
        line-height: 1.1;
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
    </style>
    """,
    unsafe_allow_html=True,
)

GAME_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "game_state"
GAME_STATE_DIR.mkdir(exist_ok=True)
LEADERBOARD_CSV = GAME_STATE_DIR / "leaderboard.csv"
LEADERBOARD_COLUMNS = ["Time", "Team", "Mode", "Probability of ruin", "Asset classes used"]


@st.cache_data(show_spinner=False)
def _cached_load_asset_returns(_mtime: float) -> pd.DataFrame:
    return load_asset_returns()


_asset_returns_mtime = (DATA_DIR / "asset_class_returns.csv").stat().st_mtime
asset_df = _cached_load_asset_returns(_asset_returns_mtime)
cpi = load_cpi(asset_df)


@st.cache_data(show_spinner=False)
def _benchmark_prob_ruin(name, _asset_df, _cpi, profile):
    """Cached per (portfolio name, profile) - independent of any player's own allocation, so every
    team playing with the same host-set client profile shares one cached run instead of
    re-simulating Four Seasons/Better on every single reveal click."""
    return run_simulation(name, _asset_df, _cpi, profile, method="stationary_block",
                           n_sims=2000, seed=42).prob_ruin


def _load_leaderboard() -> pd.DataFrame:
    if LEADERBOARD_CSV.exists():
        try:
            return pd.read_csv(LEADERBOARD_CSV)
        except pd.errors.EmptyDataError:
            pass
    return pd.DataFrame(columns=LEADERBOARD_COLUMNS)


def _append_leaderboard(row: dict):
    df = pd.concat([_load_leaderboard(), pd.DataFrame([row])], ignore_index=True)
    df.to_csv(LEADERBOARD_CSV, index=False)


def _stat_card(label, value, color=None):
    color_style = f"color:{color};" if color else ""
    st.markdown(
        f"<div class='stat-card'><div class='label'>{label}</div>"
        f"<div class='value' style='{color_style}'>{value}</div></div>",
        unsafe_allow_html=True,
    )


def _tier(prob_ruin):
    if prob_ruin < 0.05:
        return "Excellent", "🏆", COLOR_GOOD, "Retirement royalty. This plan just about never runs dry."
    elif prob_ruin < 0.15:
        return "Good", "✅", COLOR_GOOD, "A solid, sensible plan. Nice work."
    elif prob_ruin < 0.30:
        return "Risky", "⚠️", COLOR_WARN, "Living a little dangerously - some futures don't end well."
    else:
        return "High risk", "💀", COLOR_BAD, "Back to the drawing board - this pot runs out a lot."


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
    "<div class='game-hero'><h1>🎮 Build Your Own Portfolio</h1>"
    "<p>Assign weightings (and fees) across asset classes, then find out how likely your portfolio "
    "is to run out of money in retirement. Runs on the exact same simulation engine and market data "
    "as the main Mobius Wealth comparison tool - nothing here is a simplified stand-in. Play on your "
    "own device - everyone's score lands on the shared leaderboard at the bottom of the page. 🏁</p>"
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
    st.divider()
    st.caption(f"Leaderboard has {len(_load_leaderboard())} entries.")
    if st.button("🗑️ Clear leaderboard (start a new game)"):
        pd.DataFrame(columns=LEADERBOARD_COLUMNS).to_csv(LEADERBOARD_CSV, index=False)
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
weights_ok = abs(total_weight - 100.0) < 0.51
count_ok = 0 < selected_count <= max_classes
name_ok = bool(team_name.strip())
can_reveal = weights_ok and count_ok and name_ok

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

progress_col, count_col, name_col = st.columns(3)
with progress_col:
    st.progress(min(total_weight / 100.0, 1.0))
    _stat_card("Total allocated", f"{total_weight:.1f}% / 100%",
               COLOR_GOOD if weights_ok else None)
    st.caption(build_stage)
with count_col:
    _stat_card("Asset classes used", f"{selected_count} / {max_classes}",
               COLOR_GOOD if count_ok else COLOR_BAD if selected_count else None)
with name_col:
    _stat_card("Team name set", "Yes ✅" if name_ok else "No ❌",
               COLOR_GOOD if name_ok else COLOR_BAD)

if not weights_ok:
    st.warning("Your weights need to add up to 100% before you can build your portfolio.")
if not count_ok and selected_count > 0:
    st.warning(f"You've used {selected_count} asset classes - the limit for this game is {max_classes}. "
               f"Zero out some rows to get under the limit.")
if not name_ok:
    st.warning("Enter a team / player name above so your score can go on the leaderboard.")

reveal = st.button("🎯 Build my portfolio & reveal my score", type="primary",
                    disabled=not can_reveal, use_container_width=True)

result_key = f"game_result_{granularity}"

if reveal:
    rows = edited[edited["Weight %"] > 0]
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

    profile = ClientProfile(starting_age=age, horizon_years=horizon, starting_pot=float(pot),
                             initial_annual_spend=float(spend))
    result = run_simulation("Your portfolio", asset_df, cpi, profile, method="stationary_block",
                             n_sims=2000, seed=42, custom_weights=weights, custom_fee=custom_fee)
    st.session_state[result_key] = result.prob_ruin
    _append_leaderboard({
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Team": team_name.strip(),
        "Mode": granularity,
        "Probability of ruin": round(result.prob_ruin * 100, 2),
        "Asset classes used": selected_count,
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
    if prob_ruin < 0.05:
        st.balloons()

    profile = ClientProfile(starting_age=age, horizon_years=horizon, starting_pot=float(pot),
                             initial_annual_spend=float(spend))
    four_seasons_ruin = _benchmark_prob_ruin("Four Seasons", asset_df, cpi, profile)
    better_ruin = _benchmark_prob_ruin("Better", asset_df, cpi, profile)

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

    if st.button("🔁 Build another portfolio"):
        del st.session_state[result_key]
        st.rerun()

st.divider()
st.markdown("### 🏆 Leaderboard")
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
    st.dataframe(ranked, hide_index=True, use_container_width=True)
