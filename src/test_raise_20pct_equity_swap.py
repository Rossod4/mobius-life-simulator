"""
Hugh's request after meeting Dan: put 20% into [RAISE] in place of equities, alongside Better's
other diversifiers, and see the difference. Unlike test_raise_in_better.py (which swapped RAISE
for Better's small 5% Commodities slot), this cuts the EQUITY sleeve specifically - Better's
existing non-equity diversifiers (bonds, credit, property, hedge strategies, commodities - 65% of
the portfolio) are left at their current absolute weights entirely untouched ("alongside our other
diversifiers"); only equity is reduced, proportionally within itself, from its current 35% down to
15%, and the freed 20 percentage points go into each RAISE variant in turn.

Run: `python test_raise_20pct_equity_swap.py`
"""
import pandas as pd

from engine import load_asset_returns, load_cpi, ClientProfile, run_simulation, downside_stats
from portfolios import AC, asset_class_weights, weighted_avg_fee, EQUITY_CLASSES

RAISE_RETURNS_CSV = "../data/equities/raise_index_returns.csv"
EQUITY_CUT_PP = 0.20  # percentage points moved from equity into RAISE

pd.set_option("display.width", 120)


def equity_reduced_weights(base_weights, cut_pp):
    """Scales Better's equity sleeve down by `cut_pp` percentage points (proportionally within
    equity), leaving every non-equity holding's ABSOLUTE weight unchanged - i.e. the freed
    percentage points come entirely out of equity, not out of the diversifiers too."""
    is_eq = base_weights.index.isin(EQUITY_CLASSES)
    base_equity_total = base_weights[is_eq].sum()
    target_equity_total = base_equity_total - cut_pp
    assert target_equity_total >= 0, f"cut_pp {cut_pp} exceeds current equity weight {base_equity_total}"
    scaled = base_weights.copy().astype(float)
    scaled[is_eq] = base_weights[is_eq] * (target_equity_total / base_equity_total)
    return scaled


def main():
    asset_df = load_asset_returns()
    cpi = load_cpi(asset_df)
    raise_df = pd.read_csv(RAISE_RETURNS_CSV, index_col=0, parse_dates=True)

    blended_df = asset_df.join(raise_df, how="outer")
    for col in raise_df.columns:
        AC[col] = col

    better_fee = weighted_avg_fee("Better")
    base_weights = asset_class_weights("Better")
    reduced_eq_weights = equity_reduced_weights(base_weights, EQUITY_CUT_PP)

    profile = ClientProfile(starting_age=65, horizon_years=30, starting_pot=500_000.0,
                             initial_annual_spend=20_000.0)

    variants = {
        "Better (current)": None,
        "Better, -20pp equity + RAISE": "RAISE",
        "Better, -20pp equity + RAISE Mom Leaders": "RAISE + Mom Leaders",
        "Better, -20pp equity + RAISE Low Vol Leaders": "RAISE + Low Vol Leaders",
    }

    rows = []
    for label, replacement in variants.items():
        if replacement is None:
            weights = base_weights.copy()
        else:
            weights = reduced_eq_weights.copy()
            weights[replacement] = EQUITY_CUT_PP
        assert abs(weights.sum() - 1.0) < 1e-9, f"{label}: weights sum to {weights.sum()}, not 1.0"
        res = run_simulation(label, blended_df, cpi, profile, n_sims=2000, seed=42,
                              custom_weights=weights, custom_fee=better_fee)
        s = res.summary()
        dd = downside_stats(label, blended_df, custom_weights=weights, custom_fee=better_fee)
        rows.append({
            "Variant": label,
            "Probability of ruin": s["Probability of ruin"],
            "Median legacy": s["Median legacy"],
            "Max DD": dd["maxdd"],
            "Average DD": dd["avgdd"],
        })

    df = pd.DataFrame(rows)
    print("=" * 100)
    print("Mobius Better: 20% into each RAISE variant IN PLACE OF EQUITY (35% -> 15%),")
    print("other diversifiers (bonds/credit/property/hedge/commodities, 65% of the portfolio) unchanged")
    print("(age 65, £500,000 pot, £20,000/yr, 30-year horizon)")
    print("=" * 100)
    print(df.to_string(index=False, formatters={
        "Probability of ruin": "{:.1%}".format,
        "Median legacy": "£{:,.0f}".format,
        "Max DD": "{:.1%}".format,
        "Average DD": "{:.1%}".format,
    }))


if __name__ == "__main__":
    main()
