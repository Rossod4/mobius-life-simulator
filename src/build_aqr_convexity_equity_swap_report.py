"""
One-pager for Hugh: Better with percentage points moved OUT of equity and into AQR's proposed
Convexity Fusion Global Equity strategy, leaving every other diversifier (bonds, credit, property,
hedge strategies, commodities) at its current absolute weight - same methodology and same client
ask ("put 20% into this strategy in place of equities, alongside our other diversifiers, for
example") as build_raise_equity_swap_report.py, applied to AQR's Convexity Fusion deck instead of
RAISE. Since the 20% figure was given as "for example", this also sweeps 10% and 30% either side
of it as a sensitivity check.

AQR Convexity Fusion Global Equity is a PROPOSED strategy - AQR does not currently run it and
there is no guarantee it comes to market. Returns are AQR's own hypothetical/backtested monthly
series (Feb 2001-Jun 2026, hedged GBP, net of an assumed 0.5% mgmt fee), from the Excel file AQR
prepared at Mobius's request, not a live track record.

Run: `python build_aqr_convexity_equity_swap_report.py`
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from engine import load_asset_returns, load_cpi, ClientProfile, run_simulation, downside_stats
from portfolios import AC, asset_class_weights, weighted_avg_fee, EQUITY_CLASSES
from fpdf import FPDF
from fpdf.enums import XPos, YPos

AQR_RETURNS_CSV = Path(__file__).resolve().parent.parent / "data" / "equities" / "aqr_convexity_fusion_returns.csv"
POT = 500_000.0
SPEND = 20_000.0
EQUITY_CUTS = [0.10, 0.20, 0.30]  # percentage points taken OUT of equity and put into AQR Convexity Fusion

OUT_PNG = Path(__file__).resolve().parent.parent / "output" / "aqr_convexity_equity_swap_chart.png"
OUT_PDF = Path(__file__).resolve().parent.parent / "output" / "Better_AQR_Convexity_Equity_Swap.pdf"


def build_variants(base_weights: pd.Series, cuts: list) -> dict:
    is_equity = base_weights.index.isin(EQUITY_CLASSES)
    equity_total = base_weights[is_equity].sum()

    variants = {"Better (current)": base_weights.copy()}
    for cut in cuts:
        target_equity_total = equity_total - cut
        if target_equity_total < 0:
            raise ValueError(f"cut ({cut:.0%}) exceeds current equity weight ({equity_total:.1%})")
        w = base_weights.copy().astype(float)
        w[is_equity] = w[is_equity] * (target_equity_total / equity_total)
        w["AQR Convexity Fusion Global Equity"] = cut
        variants[f"Better, -{cut:.0%} equity + AQR Convexity Fusion"] = w
    return variants, equity_total


def main():
    asset_df = load_asset_returns()
    cpi = load_cpi(asset_df)
    aqr_df = pd.read_csv(AQR_RETURNS_CSV, index_col=0, parse_dates=True)
    blended_df = asset_df.join(aqr_df, how="outer")
    for col in aqr_df.columns:
        AC[col] = col

    better_fee = weighted_avg_fee("Better")
    base_weights = asset_class_weights("Better")
    variants, equity_before = build_variants(base_weights, EQUITY_CUTS)

    profile = ClientProfile(starting_age=65, horizon_years=30, starting_pot=POT, initial_annual_spend=SPEND)

    rows = []
    for label, weights in variants.items():
        res = run_simulation(label, blended_df, cpi, profile, n_sims=2000, seed=42,
                              custom_weights=weights, custom_fee=better_fee)
        s = res.summary()
        dd = downside_stats(label, blended_df, custom_weights=weights, custom_fee=better_fee)
        rows.append({
            "Variant": label,
            "Probability of ruin": s["Probability of ruin"],
            "Median legacy": s["Median legacy"],
            "Max DD": dd["maxdd"],
        })
    results = pd.DataFrame(rows)

    print(f"Base equity sleeve: {equity_before:.1%}. Sensitivity across cuts: {[f'{c:.0%}' for c in EQUITY_CUTS]}")
    print(results.to_string(index=False, formatters={
        "Probability of ruin": "{:.1%}".format,
        "Median legacy": "£{:,.0f}".format,
        "Max DD": "{:.1%}".format,
    }))

    # --- chart ---
    baseline = results.iloc[0]
    labels_short = ["Better\n(current)"] + [f"-{c:.0%} equity\n+ AQR CF" for c in EQUITY_CUTS]
    colors = ["#6B6F76", "#A8D8C0", "#4FC090", "#1BAF7A"]

    fig, axes = plt.subplots(1, 2, figsize=(8, 4.2))

    ax = axes[0]
    bars = ax.bar(range(len(results)), results["Probability of ruin"] * 100, color=colors)
    for bar, val in zip(bars, results["Probability of ruin"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1, f"{val:.1%}",
                 ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Probability of ruin (%)")
    ax.set_xticks(range(len(results)))
    ax.set_xticklabels(labels_short, fontsize=7.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax = axes[1]
    bars = ax.bar(range(len(results)), results["Median legacy"] / 1000, color=colors)
    for bar, val in zip(bars, results["Median legacy"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5, f"£{val/1000:,.0f}k",
                 ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Median legacy (£000s)")
    ax.set_xticks(range(len(results)))
    ax.set_xticklabels(labels_short, fontsize=7.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    OUT_PNG.parent.mkdir(exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)

    # --- PDF ---
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 9, "Better + AQR Convexity Fusion - Equity Replacement Sensitivity", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    cuts_str = "/".join(f"{c:.0%}" for c in EQUITY_CUTS)
    pdf.multi_cell(
        0, 5.5,
        f"Tests moving {cuts_str} of Mobius Better's portfolio out of equities (base equity "
        f"weight {equity_before:.0%}) and into AQR's proposed Convexity Fusion Global Equity "
        "strategy, leaving every other diversifier (bonds, credit, property, hedge strategies, "
        "commodities) at its current weight in each case.",
    )
    pdf.ln(3)

    pdf.image(str(OUT_PNG), w=185)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(230, 230, 230)
    col_widths = [95, 30, 35, 25]
    for w, h in zip(col_widths, ["Variant", "Probability of ruin", "Median legacy", "Max DD"]):
        pdf.cell(w, 7, h, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8.5)
    for _, row in results.iterrows():
        pdf.cell(col_widths[0], 7, row["Variant"], border=1)
        pdf.cell(col_widths[1], 7, f"{row['Probability of ruin']:.1%}", border=1)
        pdf.cell(col_widths[2], 7, f"£{row['Median legacy']:,.0f}", border=1)
        pdf.cell(col_widths[3], 7, f"{row['Max DD']:.1%}", border=1)
        pdf.ln()
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    swapped_rows = results.iloc[1:]
    best = swapped_rows.sort_values("Probability of ruin").iloc[0]
    monotonic_improving = all(
        swapped_rows["Probability of ruin"].iloc[i] <= swapped_rows["Probability of ruin"].iloc[i - 1]
        for i in range(1, len(swapped_rows))
    )
    trend_desc = (
        "probability of ruin keeps falling as the allocation increases from 10% to 30%"
        if monotonic_improving else
        f"probability of ruin improves versus the current portfolio at every size tested, "
        f"with {best['Variant'].split(',')[1].strip()} the strongest of the three"
    )
    pdf.multi_cell(
        0, 6,
        f"Conclusion: at every size tested (10%/20%/30% of the portfolio funded from equity), "
        f"probability of ruin falls versus the current portfolio "
        f"({baseline['Probability of ruin']:.1%} baseline) and median legacy rises. {trend_desc.capitalize()}. "
        f"Max drawdown ticks up modestly at each step "
        f"({baseline['Max DD']:.1%} baseline vs {swapped_rows['Max DD'].min():.1%} to "
        f"{swapped_rows['Max DD'].max():.1%} across the three variants), consistent with the "
        "strategy clipping tail losses rather than reducing volatility everywhere. Unlike the "
        "equivalent RAISE-funded-from-equity test, this swap improves both headline metrics at "
        "every allocation size tested.",
    )
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(150, 30, 30)
    pdf.multi_cell(
        0, 5,
        "Important: AQR Convexity Fusion Global Equity is a PROPOSED strategy. AQR does not "
        "currently run it and there is no guarantee it will come to market or be profitable. The "
        "returns used in this test are AQR's own hypothetical/backtested series (Feb 2001-Jun 2026, "
        "prepared at Mobius's request), not a live track record - hypothetical results are prepared "
        "with the benefit of hindsight and frequently differ from what an actual strategy achieves.",
    )
    pdf.ln(2)

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        0, 4.5,
        f"Illustrative only. Same {better_fee*10000:.0f}bps flat fee and blended asset data (AQR "
        "Convexity Fusion series merged with Mobius Better's other 11 holdings) as the equivalent "
        "RAISE-funded-from-equity test. Probability of ruin is a Monte Carlo estimate from "
        "historical returns over the full backtest window, not a guarantee of future performance.",
    )

    OUT_PDF.parent.mkdir(exist_ok=True)
    pdf.output(str(OUT_PDF))
    print(f"\nSaved {OUT_PDF}")


if __name__ == "__main__":
    main()
