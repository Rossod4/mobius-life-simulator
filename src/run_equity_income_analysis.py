"""
Demo/sanity-check for the Week 5-8 individual-share decumulation framework (equity_income.py).
Uses PLACEHOLDER/SYNTHETIC share data (see generate_placeholder_equity_data.py) - replace with a
real Bloomberg export and re-run unchanged once task 12 is done.

Run: `python run_equity_income_analysis.py`
"""
import pandas as pd

from engine import load_asset_returns, load_cpi, ClientProfile
from equity_income import (
    load_equity_returns, load_share_metadata, rank_shares, evaluate_basket,
    share_correlation_matrix, find_best_baskets,
)

pd.set_option("display.width", 120)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")


def main():
    asset_df = load_asset_returns()
    cpi = load_cpi(asset_df)
    equity_df = load_equity_returns()
    meta = load_share_metadata()

    profile = ClientProfile(starting_age=65, horizon_years=30, starting_pot=500_000.0,
                             initial_annual_spend=20_000.0)

    print("=" * 78)
    print("TASK 13 - individual shares vs the 'don't run out of money' objective")
    print("=" * 78)
    ranked = rank_shares(equity_df, cpi, profile)
    ranked = ranked.merge(meta[["Ticker", "Company", "Sector"]], left_on="Share", right_on="Ticker")
    ranked = ranked[["Share", "Company", "Sector", "Probability of ruin", "Median legacy",
                      "Max DD", "Average DD", "CVaR 95 Mthly"]]
    print(ranked.to_string(index=False))

    print()
    print("=" * 78)
    print("Correlation matrix (spot low-correlation pairs worth combining - task 14)")
    print("=" * 78)
    print(share_correlation_matrix(equity_df).round(2).to_string())

    print()
    print("=" * 78)
    print("TASK 14 - systematic basket search (every 3-share equal-weight combination, ranked by")
    print("actual probability of ruin - not just a hand-picked pair)")
    print("=" * 78)
    # Search at a reduced n_sims first (~10x faster, ~134ms/combo vs ~1.4s/combo measured on this
    # data - the combinatorial count (C(n,3)) grows fast as the share universe widens, e.g. 560
    # combos for a 16-share universe, so full n_sims=2000 per combo doesn't scale for the search
    # step). This is a screening pass to find the CANDIDATE winner, not the final reported number -
    # the winning basket is re-run at full n_sims below (see TASK 16) before anything is quoted.
    SEARCH_N_SIMS = 300
    # Diversification basis is SECTOR CHARACTERISTICS, not total-return correlation (direct
    # feedback - two shares can show low historical correlation in a ~25-year sample by chance
    # without being economically diversified at all). min_sectors=3 rules out any 3-share basket
    # with two holdings from the same sector outright, however low their correlation happens to be.
    sector_map = dict(zip(meta["Ticker"], meta["Sector"]))
    top_baskets = find_best_baskets(equity_df, cpi, profile, basket_size=3, top_n=5,
                                     n_sims=SEARCH_N_SIMS, sector_map=sector_map, min_sectors=3)
    print(f"(search run at n_sims={SEARCH_N_SIMS} for speed - re-verified at full n_sims below; "
          f"restricted to baskets spanning 3 distinct sectors)")
    print(top_baskets.to_string(index=False))

    best_basket = top_baskets.iloc[0]["Basket"]
    best_tickers = best_basket.split(" + ")
    weights = {t: 1.0 / len(best_tickers) for t in best_tickers}

    print()
    print("=" * 78)
    print(f"TASK 16 - best basket found ({best_basket}), compared across 3 rebalancing approaches")
    print("=" * 78)
    for label, mode in [("Constant-mix (rebalanced monthly)", "monthly"),
                        ("Annual rebalance", "annual"),
                        ("Buy-and-hold (never rebalanced)", "buy_and_hold")]:
        res, dd = evaluate_basket(f"Best basket ({mode})", weights, equity_df, cpi, profile, rebalance=mode)
        s = res.summary()
        print(f"{label:36s} Prob. of ruin: {s['Probability of ruin']:6.2%}   "
              f"Median legacy: £{s['Median legacy']:>10,.0f}   Max DD: {dd['maxdd']:7.2%}")


if __name__ == "__main__":
    main()
