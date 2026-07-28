"""
Task 12 (internship Week 5): extract real UK share-level data from a Bloomberg Terminal export,
producing data/equities/uk_shares_returns_real.csv and data/equities/share_metadata_real.csv in the
exact shape equity_income.py already expects (see its load_equity_returns/load_share_metadata) - so
switching from placeholder to real data is a one-line change (point EQUITY_RETURNS_CSV/
SHARE_METADATA_CSV at the _real files, or just rename them over the placeholder ones) rather than a
rewrite of any downstream analysis.

------------------------------------------------------------------------------------------------
HOW TO PRODUCE THE BLOOMBERG EXPORT THIS SCRIPT EXPECTS (do this in Bloomberg Terminal / Excel first)
------------------------------------------------------------------------------------------------
This mirrors extract_data.py's existing convention exactly (same repeating-block layout as
Bloomberg_Decumulation_Data_9_July_2026.xlsx), so the same parsing logic can be reused unchanged:

1. Candidate universe: data/equities/uk_shares_universe_candidates.csv lists 16 real, long-listed
   FTSE 100 shares across 6 sectors (Consumer Staples, Healthcare, Financials, Utilities, Mining,
   Energy) - adjust the list first if you want different/more names, but keep enough sector spread
   for the basket search (task 14) to have genuine diversification to find.

2. For EACH ticker in that list, pull a MONTHLY TOTAL RETURN series (dividends reinvested, GBP,
   NOT just a bare price series - a price-only series would understate income shares' real return
   and defeat the point of testing "equities for retirement income"). In the Bloomberg Excel
   Add-in this is typically the monthly-periodicity BDH() pull on a total-return field (e.g.
   TOT_RETURN_INDEX_GROSS_DVDS), exactly as was used for the asset-class-level indices in
   Bloomberg_Decumulation_Data_9_July_2026.xlsx - ask whoever ran that original pull for the exact
   field/settings used there so this new pull is methodologically consistent with the rest of the
   model.

3. Pull as far back as Bloomberg has data for each name (ideally back to 1999-2000 to match the
   rest of this model's history; several of these companies will have less - that's fine, each
   share's own available history is used, exactly like the main app's per-portfolio history
   handling).

4. Lay the export out exactly like the existing Bloomberg file: one 3-column block per ticker
   (col 1 = Date, col 2 = Monthly Return, col 3 = blank spacer), row 1 = the ticker/company name as
   a block header, row 2 = column labels, data from row 3 down. Save as .xlsx.

5. Update SRC below to point at that file, then run: `python extract_uk_equity_data.py`

If you'd rather hand this off, this docstring + data/equities/uk_shares_universe_candidates.csv is
everything a colleague with terminal access needs to reproduce the pull.
------------------------------------------------------------------------------------------------
"""
from pathlib import Path

import openpyxl
import pandas as pd

# TODO: point this at your real Bloomberg export once produced (see instructions above).
SRC = "PASTE_PATH_TO_YOUR_BLOOMBERG_EXPORT_HERE.xlsx"
SHEET_NAME = "Bloomberg Direct Returns"  # matches extract_data.py's convention - rename if different

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "equities"
CANDIDATES_CSV = OUT_DIR / "uk_shares_universe_candidates.csv"


def extract(src=SRC, sheet_name=SHEET_NAME):
    """Same repeating-3-column-block parser as extract_data.py, applied to a share-level export
    instead of an asset-class-level one. Returns a wide DataFrame (Date index, one column per
    ticker/company name found in the export's block headers)."""
    wb = openpyxl.load_workbook(src, data_only=True)
    ws = wb[sheet_name]

    max_col = ws.max_column
    max_row = ws.max_row

    blocks = []
    col = 1
    while col <= max_col:
        header = ws.cell(row=1, column=col).value
        if header:
            blocks.append((col, str(header).strip()))
        col += 1

    print(f"Found {len(blocks)} data blocks in {src}")

    series = {}
    for start_col, name in blocks:
        dates, vals = [], []
        for r in range(3, max_row + 1):
            d = ws.cell(row=r, column=start_col).value
            v = ws.cell(row=r, column=start_col + 1).value
            if d is None:
                continue
            dates.append(pd.Timestamp(d))
            vals.append(v)
        norm_dates = pd.DatetimeIndex(dates).to_period("M").to_timestamp("M")
        s = pd.Series(vals, index=norm_dates, name=name)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        series[name] = s

    return pd.DataFrame(series)


def match_metadata(columns) -> pd.DataFrame:
    """Matches extracted block-header names back to the candidate universe's Ticker/Company/Sector
    so share_metadata_real.csv is populated automatically wherever the header naming lines up -
    anything left unmatched is printed so it can be fixed by hand (Bloomberg block headers won't
    always come back as exactly 'Ticker' - e.g. they may be the company name or 'TICKER LN Equity')."""
    candidates = pd.read_csv(CANDIDATES_CSV)
    rows = []
    unmatched = []
    for col in columns:
        key = col.strip().upper()
        match = candidates[
            (candidates["Ticker"].str.upper() == key)
            | (candidates["BloombergTicker"].str.upper() == key)
            | (candidates["Company"].str.upper() == key)
        ]
        if len(match):
            row = match.iloc[0]
            rows.append({"Ticker": col, "Company": row["Company"], "Sector": row["Sector"]})
        else:
            unmatched.append(col)
            rows.append({"Ticker": col, "Company": col, "Sector": "Unknown - fix by hand"})
    if unmatched:
        print("Could not auto-match metadata for:", unmatched, "- edit share_metadata_real.csv by hand.")
    return pd.DataFrame(rows)


def main():
    if not Path(SRC).exists():
        print(
            f"SRC ({SRC}) not found - this script is ready to run but needs a real Bloomberg export "
            "first. See the docstring at the top of this file for exactly what to pull and how to "
            "lay it out."
        )
        return
    df = extract()
    meta = match_metadata(df.columns)

    returns_out = OUT_DIR / "uk_shares_returns_real.csv"
    meta_out = OUT_DIR / "share_metadata_real.csv"
    df.to_csv(returns_out)
    meta.to_csv(meta_out, index=False)
    print(f"Saved {returns_out} {df.shape} and {meta_out} {meta.shape}")
    print(
        "\nNext step: point equity_income.py's EQUITY_RETURNS_CSV/SHARE_METADATA_CSV at these two "
        "_real files (or rename them over the placeholder ones) and re-run "
        "run_equity_income_analysis.py - every downstream function (rank_shares, find_best_baskets, "
        "evaluate_basket, share_correlation_matrix) works unchanged."
    )


if __name__ == "__main__":
    main()
