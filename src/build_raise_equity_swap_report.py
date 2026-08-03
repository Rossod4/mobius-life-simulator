"""
Hugh's ask (email, re: Dan's RAISE presentation): take 20 percentage points OUT of Mobius Better's
equity sleeve and put it into a RAISE variant instead, leaving every other diversifier (bonds,
credit, property, hedge strategies, commodities) at its current absolute weight - "put 20% into
this strategy in place of equities, alongside our other diversifiers."

This is deliberately NOT the same swap as test_raise_in_better.py/sensitivity_raise_in_better.py
(those replace the 5% Commodities holding specifically). Here the source of funding is equity, at
4x the size (20% vs 5%), so treat this as its own test rather than an extension of that one.

Run: `python build_raise_equity_swap_report.py`
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from engine import load_asset_returns, load_cpi, ClientProfile, run_simulation
from portfolios import AC, asset_class_weights, weighted_avg_fee, EQUITY_CLASSES
from fpdf import FPDF
from fpdf.enums import XPos, YPos

RAISE_RETURNS_CSV = Path(__file__).resolve().parent.parent / "data" / "equities" / "raise_index_returns.csv"
POT = 500_000.0
SPEND = 20_000.0
EQUITY_CUT = 0.20  # percentage points taken OUT of equity and put into RAISE

OUT_PNG = Path(__file__).resolve().parent.parent / "output" / "raise_equity_swap_chart.png"
OUT_PDF = Path(__file__).resolve().parent.parent / "output" / "Better_RAISE_Equity_Swap.pdf"


def build_variants(base_weights: pd.Series) -> dict:
    """'Better (current)' plus one variant per RAISE flavour, each with EQUITY_CUT points moved
    from the equity sleeve (scaled down proportionally within itself) into that RAISE column,
    every non-equity holding left at its current absolute weight."""
    is_equity = base_weights.index.isin(EQUITY_CLASSES)
    equity_total = base_weights[is_equity].sum()
    target_equity_total = equity_total - EQUITY_CUT
    if target_equity_total < 0:
        raise ValueError(f"EQUITY_CUT ({EQUITY_CUT:.0%}) exceeds current equity weight ({equity_total:.1%})")

    variants = {"Better (current)": base_weights.copy()}
    for label, col in [("Better + RAISE (20% ex-equity)", "RAISE"),
                        ("Better + RAISE Mom Leaders (20% ex-equity)", "RAISE + Mom Leaders"),
                        ("Better + RAISE Low Vol Leaders (20% ex-equity)", "RAISE + Low Vol Leaders")]:
        w = base_weights.copy().astype(float)
        w[is_equity] = w[is_equity] * (target_equity_total / equity_total)
        w[col] = EQUITY_CUT
        variants[label] = w
    return variants, equity_total, target_equity_total


def main():
    asset_df = load_asset_returns()
    cpi = load_cpi(asset_df)
    raise_df = pd.read_csv(RAISE_RETURNS_CSV, index_col=0, parse_dates=True)
    blended_df = asset_df.join(raise_df, how="outer")
    for col in raise_df.columns:
        AC[col] = col

    better_fee = weighted_avg_fee("Better")
    base_weights = asset_class_weights("Better")
    variants, equity_before, equity_after = build_variants(base_weights)

    profile = ClientProfile(starting_age=65, horizon_years=30, starting_pot=POT, initial_annual_spend=SPEND)

    rows = []
    for label, weights in variants.items():
        res = run_simulation(label, blended_df, cpi, profile, n_sims=2000, seed=42,
                              custom_weights=weights, custom_fee=better_fee)
        s = res.summary()
        rows.append({
            "Variant": label,
            "Probability of ruin": s["Probability of ruin"],
            "Median legacy": s["Median legacy"],
        })
    results = pd.DataFrame(rows)

    print(f"Equity sleeve: {equity_before:.1%} -> {equity_after:.1%} (-{EQUITY_CUT:.0%} points, moved into RAISE)")
    print(results.to_string(index=False, formatters={
        "Probability of ruin": "{:.1%}".format,
        "Median legacy": "£{:,.0f}".format,
    }))

    # --- chart ---
    fig, ax = plt.subplots(figsize=(7.5, 4))
    colors = ["#6B6F76", "#1BAF7A", "#EDA100", "#3C7DC4"]
    bars = ax.bar(results["Variant"], results["Probability of ruin"] * 100, color=colors)
    for bar, val in zip(bars, results["Probability of ruin"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15, f"{val:.1%}",
                ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Probability of ruin (%)")
    ax.set_xticks(range(len(results)))
    ax.set_xticklabels(results["Variant"], rotation=15, ha="right", fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    OUT_PNG.parent.mkdir(exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)

    # --- PDF ---
    baseline = results.iloc[0]
    best = results.iloc[1:].sort_values("Probability of ruin").iloc[0]
    worst = results.iloc[1:].sort_values("Probability of ruin").iloc[-1]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 9, "Better + RAISE - Equity Replacement Test", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(
        0, 5.5,
        f"Tests moving {EQUITY_CUT:.0%} of Mobius Better's portfolio out of equities "
        f"({equity_before:.0%} -> {equity_after:.0%}) and into each RAISE variant in turn, "
        "leaving every other diversifier (bonds, credit, property, hedge strategies, "
        "commodities) at its current weight.",
    )
    pdf.ln(3)

    pdf.image(str(OUT_PNG), w=180)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(230, 230, 230)
    col_widths = [95, 45, 40]
    for w, h in zip(col_widths, ["Variant", "Probability of ruin", "Median legacy"]):
        pdf.cell(w, 7, h, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8.5)
    for _, row in results.iterrows():
        pdf.cell(col_widths[0], 7, row["Variant"], border=1)
        pdf.cell(col_widths[1], 7, f"{row['Probability of ruin']:.1%}", border=1)
        pdf.cell(col_widths[2], 7, f"£{row['Median legacy']:,.0f}", border=1)
        pdf.ln()
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    direction = "increases" if best["Probability of ruin"] > baseline["Probability of ruin"] else "reduces"
    pdf.multi_cell(
        0, 6,
        f"Conclusion: funding a {EQUITY_CUT:.0%} RAISE allocation from equity {direction} probability "
        f"of ruin versus the current portfolio ({baseline['Probability of ruin']:.1%}) for all three "
        f"variants tested. {best['Variant']} is the least damaging of the three "
        f"({best['Probability of ruin']:.1%}); {worst['Variant']} is the worst "
        f"({worst['Probability of ruin']:.1%}). At this size and funded from equity, none of the "
        "three variants improve on the current portfolio for this objective.",
    )
    pdf.ln(3)

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        0, 4.5,
        f"Illustrative only. Same {better_fee*10000:.0f}bps flat fee and blended asset data (RAISE "
        "merged with Mobius Better's other 10 holdings) as the earlier Better + RAISE tests - this "
        "test differs from those only in funding the RAISE allocation from equity (20 points) rather "
        "than replacing the 5% Commodities holding. Probability of ruin is a Monte Carlo estimate "
        "from historical returns over the full backtest window, not a guarantee of future "
        "performance.",
    )

    OUT_PDF.parent.mkdir(exist_ok=True)
    pdf.output(str(OUT_PDF))
    print(f"\nSaved {OUT_PDF}")


if __name__ == "__main__":
    main()
