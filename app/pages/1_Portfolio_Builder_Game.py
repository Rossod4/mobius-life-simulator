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

st.title("🎮 Build Your Own Portfolio")
st.caption(
    "Assign weightings (and fees) across asset classes, then find out how likely your portfolio is "
    "to run out of money in retirement. Runs on the exact same simulation engine and market data as "
    "the main Mobius Wealth comparison tool - nothing here is a simplified stand-in. Play on your "
    "own device - everyone's score lands on the shared leaderboard at the bottom of the page."
)

with st.expander("Game setup (host controls)", expanded=False):
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
    "Asset classes",
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

team_name = st.text_input("Team / player name", key="team_name",
                           help="Shown on the leaderboard - pick something your team will recognise.")

st.markdown("#### Your allocation")
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
        "Not selectable yet (no return data in the model): " + ", ".join(UNAVAILABLE_CATEGORIES)
        + " — these are on the fund store's own asset-class list but don't have historical return "
          "series behind them here, so they're left out rather than guessed at."
    )

total_weight = float(edited["Weight %"].sum())
selected_count = int((edited["Weight %"] > 0).sum())
weights_ok = abs(total_weight - 100.0) < 0.51
count_ok = 0 < selected_count <= max_classes
name_ok = bool(team_name.strip())
can_reveal = weights_ok and count_ok and name_ok

progress_col, count_col, name_col = st.columns([2, 1, 1])
with progress_col:
    st.progress(min(total_weight / 100.0, 1.0))
    st.caption(f"Total allocated: {total_weight:.1f}% / 100%")
with count_col:
    st.metric("Asset classes used", f"{selected_count} / {max_classes}")
with name_col:
    st.metric("Team name set", "Yes" if name_ok else "No")

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
    if prob_ruin < 0.05:
        tier, emoji = "Excellent", "🏆"
    elif prob_ruin < 0.15:
        tier, emoji = "Good", "✅"
    elif prob_ruin < 0.30:
        tier, emoji = "Risky", "⚠️"
    else:
        tier, emoji = "High risk", "💀"
    st.markdown(f"## {emoji} Probability of ruin: **{prob_ruin * 100:.1f}%**")
    st.markdown(f"### Verdict: {tier}")
    if prob_ruin < 0.05:
        st.balloons()

    profile = ClientProfile(starting_age=age, horizon_years=horizon, starting_pot=float(pot),
                             initial_annual_spend=float(spend))
    four_seasons_ruin = _benchmark_prob_ruin("Four Seasons", asset_df, cpi, profile)
    better_ruin = _benchmark_prob_ruin("Better", asset_df, cpi, profile)

    st.markdown("#### How you compare")
    bcol1, bcol2, bcol3 = st.columns(3)
    bcol1.metric("Your portfolio", f"{prob_ruin * 100:.1f}%")
    bcol2.metric(PORTFOLIO_META.get("Four Seasons", {}).get("DisplayName", "Aspen Four Seasons"),
                 f"{four_seasons_ruin * 100:.1f}%")
    bcol3.metric(PORTFOLIO_META.get("Better", {}).get("DisplayName", "Mobius Better"),
                 f"{better_ruin * 100:.1f}%")
    beat_fs = prob_ruin < four_seasons_ruin
    beat_better = prob_ruin < better_ruin
    if beat_better:
        st.success("You beat Mobius Better - the tool's own most diversified construction. Impressive.")
    elif beat_fs:
        st.info("You beat Aspen Four Seasons, but Mobius Better still edges you out.")
    else:
        st.info("Both benchmark portfolios currently beat you - room to improve.")

    if st.button("Build another portfolio"):
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
    ranked.index = ranked.index + 1
    ranked.index.name = "Rank"
    st.dataframe(ranked, use_container_width=True)
