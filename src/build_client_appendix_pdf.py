"""
Client Appendix: "How This Model Works" - the methodology/assumptions companion to the one-page
summary PDF (app.py's build_summary_pdf references it: "See attached Appendix for assumptions
used"). A static explainer, not a live data pull - the numbers quoted here (fees, portfolio shape,
data windows) are facts about the CURRENT model configuration, not recomputed per run, so they need
to be kept in sync by hand if the underlying portfolios/fees change (see weighted_avg_fee /
asset_class_weights calls below, used once at generation time to catch any drift before it ships).

Rebuilt from the rendered PDF text (no prior source script existed in this repo) with tighter
spacing between sections and the same merged one-paragraph legal footer as the summary PDF.

Run: `python build_client_appendix_pdf.py`
"""
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from portfolios import weighted_avg_fee

OUT_PDF = Path(__file__).resolve().parent.parent / "output" / "Mobius_Wealth_Client_Appendix.pdf"

GREY = (90, 90, 90)
BLACK = (20, 20, 20)
LIGHT_GREY = (140, 140, 140)


def h1(pdf, text):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*BLACK)
    pdf.cell(0, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)


def h2(pdf, text):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*BLACK)
    pdf.cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def body(pdf, text, size=9.5, gap=2):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", size)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 4.6, text)
    pdf.ln(gap)


def bullet(pdf, label, text, size=9.5, gap=1.5):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", size)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 4.6, f"- {label}:")
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", size)
    pdf.multi_cell(0, 4.6, f"  {text}")
    pdf.ln(gap)


def table(pdf, headers, rows, col_widths):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(230, 230, 230)
    for w, htext in zip(col_widths, headers):
        pdf.cell(w, 6.5, htext, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8.5)
    for row in rows:
        pdf.set_x(pdf.l_margin)
        for w, cell in zip(col_widths, row):
            pdf.cell(w, 6.5, cell, border=1)
        pdf.ln()
    pdf.ln(2)


def build():
    fee_fs = weighted_avg_fee("Four Seasons") * 100
    fee_better = weighted_avg_fee("Better") * 100

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*BLACK)
    pdf.cell(0, 9, "Appendix: How This Model Works", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 6, "Full methodology, data sources and assumptions behind every figure in this summary",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    h1(pdf, "1. What this model does")
    body(pdf,
         "This tool compares how a pension pot might perform under different portfolios during "
         "Decumulation - drawing an income from the pot after retirement. Rather than assuming one "
         "fixed future, it tests each portfolio against thousands of different ways real historical "
         "market patterns could have played out, to show a realistic RANGE of outcomes rather than a "
         "single guess.")

    h1(pdf, "2. Where every number comes from")
    body(pdf, "Nothing in this model is invented or estimated where a real source exists. Every input "
              "traces back to:", gap=1.5)
    table(pdf, ["Data", "Source", "Used for"], [
        ["Asset-class returns", "Bloomberg (14 Jul 2026)", "Every simulation shown in this summary"],
        ["Mobius Better's data", "Previous Mobius model's own data", "Better's construction (2001-2025 window)"],
        ["Fund holdings & fees", "FNZ holdings files (9/14 Jul 2026)", "Portfolio construction"],
        ["Cash rate", "Bank of England SONIA", "Cash holdings (replaces an unusable Bloomberg column)"],
        ["UK inflation (CPI)", "Bloomberg", "Inflation-linked spending - always applied, not optional"],
        ["State Pension amount", "gov.uk, 2026/27 rates",
         "Included in the reported income figures - always applied, not optional"],
    ], [38, 55, 90])
    body(pdf,
         "Where an individual fund's own history was too short to test reliably over a 25-30 year "
         "horizon (some as little as ~1 year), its returns are represented by the closest-matching "
         "broad market index instead of the fund's own short data - the mapping used for every "
         "holding is available on request, and can be viewed and edited directly within the tool.")

    h1(pdf, "3. The portfolios being compared")
    body(pdf,
         "Two portfolios are compared in this summary (the tool can compare any registered portfolio, "
         "not just these). Fee figures below are the weighted-average ongoing charge across all of a "
         "portfolio's holdings.", gap=1.5)
    table(pdf, ["Portfolio", "Broad shape", "Wtd. fee"], [
        ["Aspen Four Seasons", "~31% growth assets, ~56% bonds/gilts/cash, ~13% commodities",
         f"{fee_fs:.2f}% pa"],
        ["Mobius Better", "~35% growth-strategy assets, ~65% bonds/credit/property/hedge strategies",
         f"{fee_better:.2f}% pa"],
    ], [38, 118, 27])
    body(pdf,
         "Mobius Better is a more diversified construction, built and tested directly against this "
         "simulation engine; it is flagged as one reasonable diversified approach, not the only "
         "possible one.")

    h1(pdf, "4. How the simulation works (\"Monte Carlo\" modelling)")
    body(pdf,
         "Around 25 years of real monthly market returns are available for each portfolio (2001-2025 "
         "for Mobius Better specifically, since its own data starts later). To test a 30-year plan "
         "properly, the model needs to see many more possible sequences of good and bad years than "
         "the 25 that actually happened, so it draws thousands of alternative but equally realistic "
         "paths by resampling chunks of the REAL historical months in different orders and "
         "combinations - a standard statistical technique called a bootstrap. The model never invents "
         "a return that didn't happen; it tests many different plausible orderings and combinations "
         "of real history instead.", gap=1.5)
    h2(pdf, "The default method: \"stationary block bootstrap\"")
    body(pdf,
         "Rather than shuffling individual months at random (which would break up realistic runs of "
         "good or bad months), the model cuts history into random-length chunks - typically a few "
         "months to a couple of years long - and stitches thousands of these chunks together to "
         "build each simulated 30-year path. This keeps realistic \"streaks\" intact (e.g. a "
         "multi-year market downturn stays together as a downturn, rather than being broken into "
         "isolated random months), which is a more realistic test than assuming every month is "
         "independent of the last. Crucially, each portfolio's mix of asset classes is blended into "
         "ONE return series before this resampling happens, so the real historical relationship "
         "between different investments (and inflation) moving together in a given month is "
         "preserved exactly, not reconstructed artificially.")
    body(pdf,
         "Three alternative methods are also available in the tool for comparison, each resampling "
         "the same real history differently: a simple month-by-month shuffle (treats every month as "
         "fully independent - the simplest approach); a fixed 12-month block shuffle; and a "
         "statistical model fitted to the shape of historical returns (a skew-normal distribution, "
         "used as a fast proxy for modelling asymmetric, crash-prone return patterns - note this has "
         "somewhat thinner extreme-tail behaviour than a true skewed Student-t distribution, which is "
         "a more specialised statistical model not implemented here).")
    h2(pdf, "What \"probability of ruin\" means, and its limits")
    body(pdf,
         "By default the model runs 2,000 of these simulated 30-year futures for each portfolio. For "
         "each one, the plan is walked forward year by year, drawing inflation-linked spending out of "
         "the pot; if the pot ever reaches zero before the horizon is up, that simulated future counts "
         "as a \"ruin\". Probability of ruin is simply the share of the 2,000 futures where this "
         "happened, shown with a confidence range reflecting the fact that 2,000 is a finite sample.")
    body(pdf,
         "Important limit, in full transparency: that confidence range only reflects the randomness "
         "of drawing 2,000 samples from the model - it does NOT capture the separate, harder question "
         "of whether the last 25 years of real market history is itself a reliable guide to the next "
         "30 years. No model can fully answer that second question.")
    body(pdf,
         "State Pension income is included in the reported cash flows and in the \"Total-income IRR\" "
         "figure below - because it is real income the client receives. This is why the summary page "
         "shows a separate \"Pot-only IRR\" figure alongside it, to isolate the portfolio's own "
         "investment return from this guaranteed, portfolio-independent income.")

    h1(pdf, "5. Every figure on the summary page, explained")
    bullet(pdf, "Probability of ruin",
           "out of the 2,000 simulated futures, the share where the pot ran out before the end of "
           "the plan. The single most important figure for judging how robust a plan is.")
    bullet(pdf, "Annualised performance",
           "the compound annual growth rate implied by the portfolio's average historical monthly "
           "return - a measure of typical investment growth, not one specific realised outcome.")
    bullet(pdf, "Volatility",
           "how much the portfolio's returns have historically bounced around year to year. Higher "
           "volatility usually means a bumpier ride, for better or worse.")
    bullet(pdf, "Cumulative performance",
           "what actually would have happened to the pot if invested on the earliest available date "
           "and left to run through the real historical sequence of returns since then - one "
           "concrete, real example, not a simulated average.")
    bullet(pdf, "IRR (internal rate of return)",
           "the client's own realised rate of return, accounting for the actual timing and size of "
           "money paid in and out - not just average growth. For Decumulation plans, two figures are "
           "shown: Total-income IRR (all cash received, including State Pension) and Pot-only IRR "
           "(the portfolio's own investment return alone, excluding State Pension). Since State "
           "Pension is the same guaranteed amount regardless of which portfolio is chosen, Pot-only "
           "IRR is the fairer way to compare portfolios against each other.")

    h1(pdf, "6. Full list of assumptions and limitations")
    body(pdf, "Every place a judgement call, simplification, or genuine limitation exists - so "
              "nothing here is a surprise:", gap=1.5)
    bullet(pdf, "Withdrawals are annual, taken at the start of the year",
           "each year's full spend is withdrawn from the pot as a single lump sum at the START of "
           "that year, before that year's investment growth is applied - not monthly, and not at "
           "year-end. This shields that year's withdrawal from that year's own market movement "
           "(neither benefiting from a rally nor exposed to a fall within the year it's taken), which "
           "differs from drawing income monthly, as many clients do in practice.")
    bullet(pdf, "Historical window is short and equity-favourable",
           "1999/2000-2026 (~25 years, or 2001-2025 for Mobius Better) is a meaningful stretch, but it "
           "is shorter than a typical 30-year retirement horizon and happened to span an unusually "
           "strong run for global equities. It does not include a 1970s-style high-inflation shock. "
           "Every figure should be read as illustrative of what this specific historical window would "
           "have produced, not a guaranteed forecast.")
    bullet(pdf, "Some fund charges are assumed, not sourced",
           "no fee data was supplied for the Aspen Four Seasons fund lineup, so typical published "
           "charges for each fund's type were used instead. Mobius Better's fees are sourced/derived "
           "directly.")
    bullet(pdf, "One fund's gold/commodity holdings use a broad proxy",
           "around 13.5% of the Aspen Four Seasons fund (gold and commodity holdings) is represented "
           "by a single broad commodities index, since no dedicated gold/resources series exists in "
           "the underlying dataset - the gold holdings' own real historical returns have been notably "
           "higher than this broad proxy, so this may understate that fund's true historical "
           "performance somewhat.")
    bullet(pdf, "Mobius Better's weights are judgement-based",
           "Mobius Better's allocation was built and tuned directly against this simulation engine, "
           "not copied from client or fund-platform data - it represents one reasonable diversified "
           "construction, not the only possible one, and is worth an independent sanity check before "
           "being relied on for advice.")
    bullet(pdf, "Tax modelling is simplified",
           "no 25% tax-free pension lump sum, and no ISA/General Investment Account modelling - the "
           "whole pot is treated as a single taxable pension wrapper. Only rest-of-UK tax bands are "
           "used (Scotland has different bands).")
    bullet(pdf, "Confidence intervals have a specific, limited scope",
           "the confidence range shown on probability-of-ruin figures reflects only the randomness of "
           "drawing a finite number of simulated paths - it does not capture whether the underlying "
           "25-year historical window is itself representative of the next 30 years.", gap=3)

    pdf.set_font("Helvetica", "", 6)
    pdf.set_text_color(*LIGHT_GREY)
    pdf.multi_cell(
        0, 3.2,
        "Mobius Life Limited is authorised by the Prudential Regulation Authority and regulated by the "
        "Financial Conduct Authority and the Prudential Regulation Authority (Mobius Life Administration "
        "Services is not authorised or regulated); Mobius Life Limited (Registered No. 3104978) and "
        "Mobius Life Administration Services (Registered No. 5754821) are registered in England and "
        "Wales at: 2nd Floor, 2 Copthall Avenue, London, EC2R 7DA.",
    )

    OUT_PDF.parent.mkdir(exist_ok=True)
    pdf.output(str(OUT_PDF))
    print(f"Saved {OUT_PDF}")


if __name__ == "__main__":
    build()
