# Mobius Wealth — Decumulation & Accumulation Simulator

A Streamlit tool that compares retirement portfolios (Mobius's own fund lineups vs a
competitor's, e.g. Aspen Advisers) on **probability of ruin** — the chance a pension pot runs
out of money before a client's plan is meant to end — using Monte Carlo simulation over real
historical market data. Includes a full client-facing comparison app and a gamified internal
version ("build your own portfolio, see if it survives").

**Live app**: https://mobius-life-simulator-czyadc2asardjl7oiuigmz.streamlit.app
**Repo**: `hasini08/mobius-life-simulator` on GitHub, `master` branch, auto-deployed via
Streamlit Community Cloud on every push.

This README is written for whoever picks this project up next — it covers what everything is,
how to run it, and where the loose ends are, not just what's "new" in the latest delivery.

## Contents

1. [Quick start](#quick-start)
2. [What's actually running](#whats-actually-running)
3. [How it fits together](#how-it-fits-together)
4. [Repository map](#repository-map)
5. [`src/` script inventory](#src-script-inventory)
6. [Data files](#data-files)
7. [Key methodology notes and assumptions](#key-methodology-notes-and-assumptions)
8. [Known gaps / where things were left off](#known-gaps--where-things-were-left-off)
9. [Deployment](#deployment)
10. [Suggested next steps](#suggested-next-steps)

## Quick start

```bash
git clone https://github.com/hasini08/mobius-life-simulator.git
cd mobius-life-simulator
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r app/requirements.txt
streamlit run app/app.py
```

Opens at `http://localhost:8501`. The Portfolio Builder Game is a second page,
auto-discovered by Streamlit from `app/pages/` — it appears in the sidebar nav automatically,
no separate command needed.

Requires Python 3.10+ (developed/tested on 3.14; the deployed Cloud runtime's exact version is
unconfirmed — see the **portability gotcha** in [Known gaps](#known-gaps--where-things-were-left-off)
before using very new type-hint syntax anywhere in `app/`).

Every module in `src/` is also independently runnable for a self-test, e.g.
`python src/tax.py` prints a self-test of the tax engine, `python src/engine.py` runs a quick
Monte Carlo comparison across the registered portfolios and prints headline stats.

## What's actually running

Two pages, one Streamlit app, both reading the same `data/` and `src/`:

- **`app/app.py`** — the main comparison tool. Pick any two (or more) registered portfolios,
  compare them across accumulation (growing the pot) and/or decumulation (spending from it).
  Headline metric is probability of ruin; also covers fan charts, legacy distributions, an
  equity allocation sweep, withdrawal-rate/guardrail sensitivity, an asset-class correlation
  heatmap, mortality-adjusted outcomes (single/joint life), UK tax + State Pension
  grossing-up, partial annuitization, and a one-page PDF export for client meetings. Portfolio
  holdings/weights/fees are **data-driven** (`data/portfolio_holdings.csv` etc.), editable
  live in the app's sidebar — adding a brand new competitor portfolio needs no code changes.
- **`app/pages/1_Portfolio_Builder_Game.py`** — a gamified internal version. Players assign
  weights and fees across the Mobius fund store's own asset-class sub-categories (or finer
  individual building blocks), hit reveal, and see only their probability of ruin — plus a
  shared cross-device leaderboard, badges, a benchmark comparison against Four Seasons/Better,
  and an interactive fan chart. Built for a live company-wide activity, not client use.

## How it fits together

```
Raw data (Bloomberg export, FNZ holdings files, Bloomberg Terminal share exports, etc.)
        │
        ▼  one-off extraction scripts (src/extract_*.py, src/build_sonia_cash.py, ...)
data/*.csv   ← the actual source of truth the app reads at runtime
        │
        ▼
src/portfolios.py   (loads portfolio holdings + asset-class map + metadata)
src/engine.py        (Monte Carlo simulation engine: run_simulation, equity_sweep, etc.)
src/mortality.py, src/tax.py, src/cma.py, src/annuity.py   (feature modules engine.py/app.py call into)
        │
        ▼
app/app.py  +  app/pages/1_Portfolio_Builder_Game.py   ← what a user actually sees
```

Everything downstream of `data/*.csv` recomputes live from that data — there are no
hardcoded results baked into the app. To add a new portfolio, asset class, or fund, edit the
relevant CSV (by hand, or via the app's own "Edit data" sidebar tab) rather than touching
`src/portfolios.py`.

## Repository map

| Path | What it is |
|---|---|
| `app/app.py` | The main Streamlit comparison app. |
| `app/pages/` | Additional Streamlit pages (currently just the Portfolio Builder Game) — auto-discovered by Streamlit, no registration needed. |
| `app/requirements.txt` | Exact pinned dependencies for both `app.py` and the game page (same environment). |
| `src/` | All Python logic — the core simulation engine, plus every one-off data-extraction/report/analysis script used to get here. See the [script inventory](#src-script-inventory) below. |
| `data/` | Cleaned CSVs the app reads at runtime — the actual source of truth. See [Data files](#data-files). |
| `data/equities/` | UK individual-share-level data (Weeks 5-8 thread) and the RAISE/AQR index data used in the equity-swap sensitivity tests. |
| `output/` | Generated deliverables (PDFs, Excel workbooks, Word docs, charts) — **gitignored**, regenerate via the relevant `src/build_*.py` script, not committed. |
| `game_state/` | Runtime state for the Portfolio Builder Game's leaderboard (`leaderboard.csv`) — **gitignored**, resets on every app restart/redeploy. See [Known gaps](#known-gaps--where-things-were-left-off). |
| `.devcontainer/` | Dev Container config, if opening this repo in a container-based IDE. |
| `.claude/launch.json` | Local dev-server shortcuts for Claude Code's browser preview tooling — not relevant to running the app normally. |

## `src/` script inventory

**Core engine — imported directly by the live app(s), this is what you'd actually edit to
change simulation behaviour:**

| File | Purpose |
|---|---|
| `engine.py` | The Monte Carlo simulation engine itself — `run_simulation`, `equity_sweep`, `sensitivity_withdrawal_rate`, `shortfall_heatmap`, `run_glide_path_simulation`, `historical_single_path`, etc. Start here to understand the methodology. |
| `portfolios.py` | Loads portfolio holdings/weights/fees, the asset-class name map, and per-portfolio display metadata from `data/*.csv`. |
| `mortality.py` | Single-life and joint-life survival-probability math (S4 pension-scheme table). |
| `tax.py` | UK income tax (rest-of-UK bands) + State Pension grossing-up. |
| `cma.py` | Forward-looking Capital Market Assumptions blend (historical bootstrap recentred towards published 10-year forecasts). |
| `annuity.py` | Partial annuitization — converting part of the pot into a guaranteed lifetime income. |

**One-off data extraction/prep — run once (or when source data changes) to (re)produce a
`data/*.csv`, not needed again otherwise:**

| File | Produces |
|---|---|
| `extract_data.py` | `data/asset_class_returns.csv`, `data/fund_returns.csv` from the Bloomberg export. |
| `build_sonia_cash.py` | Rebuilds the Cash asset-class series from the real BoE SONIA rate (the Bloomberg file's own cash column was unusable — see [methodology notes](#key-methodology-notes-and-assumptions)). |
| `build_mortality_data.py` | `data/mortality_qx.csv` from the S4 mortality table export. |
| `extract_uk_equity_data.py` | Real UK individual-share return/metadata data (Weeks 5-8 thread) from a Bloomberg Terminal export. |
| `generate_placeholder_equity_data.py` | Synthetic placeholder share data, used before the real Bloomberg Terminal export was available — superseded by `extract_uk_equity_data.py`'s output but kept for reference. |
| `load_raise_index.py` | Converts the real FTSE Russell RAISE index simulation report into `data/equities/raise_index_*.csv`. |
| `migrate_better_v4_into_main_data.py` | One-off migration that wired the validated "Better v4" construction into the main portfolio data. |

**Excel workbook build pipeline — 18 sequential stages that together build
`output/Mobius_Wealth_Decumulation_Model_v4.xlsx`, the fully formula-driven Excel-native
mirror of the app:**

`build_workbook_1.py` through `build_workbook_18.py`, plus `patch_instructions.py` (rewrites
just the workbook's Instructions sheet). Each stage's docstring names exactly what it adds
(Inputs → Portfolios → Returns → Historical Projection → Monte Carlo → Summary → Equity Sweep
→ Sensitivity Tables → Asset Correlation → Mortality → Tax → CMA → Annuity, in that order).
Run them in order from a byte-identical Excel starting point to regenerate the workbook from
scratch, or run the later stages standalone if only patching a specific sheet.

**Report/summary generators — each produces one specific deliverable in `output/`:**

| File | Produces |
|---|---|
| `build_final_summary_pdf.py`, `build_client_appendix_pdf.py` | The one-page client PDF summary + its methodology appendix (same visual format as the app's own PDF export). |
| `build_blue_box_summary.py` | A "blue box" summary workbook. |
| `build_better_v4_summary.py`, `build_recent_window_summary.py` | Standalone summary sheets for specific candidate constructions / time windows. |
| `build_equity_data_spec.py`, `build_equity_literature_review.py`, `build_equity_findings_report.py`, `build_equity_visualiser.py` | Week 5-8 internship deliverables (data extraction spec, literature review, findings writeup, editable Excel companion). |
| `build_raise_equity_swap_report.py`, `build_aqr_convexity_equity_swap_report.py` | One-pagers for Hugh testing specific "swap X% of equity for [strategy]" requests (RAISE, then AQR Convexity Fusion). |

**Individual UK equities thread (internship Weeks 5-8, tasks 13-16) — a separate, less
mature line of work from the main asset-class-level simulator:**

| File | Purpose |
|---|---|
| `equity_income.py` | The individual-share/basket decumulation testing framework itself. |
| `run_equity_income_analysis.py` | Demo/sanity-check runner for the framework above. |

**RAISE / AQR equity-swap sensitivity tests (specific stakeholder requests, not part of the
main app):**

| File | Purpose |
|---|---|
| `run_raise_index_analysis.py` | Tests the real FTSE Russell RAISE index constructions against Better. |
| `sensitivity_raise_in_better.py` | Sensitivity check on the RAISE-in-Better swap. |
| `test_raise_20pct_equity_swap.py`, `test_raise_in_better.py` | Hugh's original RAISE swap requests. |
| `test_aqr_convexity_20pct_equity_swap.py` | Same test, for AQR's Convexity Fusion strategy. |

**Verification:**

| File | Purpose |
|---|---|
| `verify_cma_annuity.py` | Cross-checks the Excel workbook's CMA blend + annuitization figures against the Python engine, to the penny. |

## Data files

- `data/portfolio_holdings.csv`, `data/asset_class_map.csv`, `data/portfolio_meta.csv`,
  `data/asset_class_comparison_groups.csv` — the actual portfolio definitions (holdings,
  weights, fees, asset-class mapping, display names). **Edit these** (by hand or via the app's
  "Edit data" tab) to add/change a portfolio — never hardcode a portfolio in `portfolios.py`.
- `data/asset_class_returns.csv` — monthly total-return series per broad asset class, the
  historical data every simulation bootstraps from. See the [portfolio-builder-game section](#known-gaps--where-things-were-left-off)
  below for which fund-store categories still have no data here.
- `data/fund_returns.csv`, `data/sonia_monthly.csv`, `data/mortality_qx.csv` — supporting
  series (individual fund histories, cash, mortality table).
- `data/equities/` — UK individual-share data (Weeks 5-8 thread) and RAISE/AQR index data
  for the equity-swap sensitivity tests. `*_real.csv` files are genuine Bloomberg Terminal
  exports; files without that suffix may be earlier/placeholder versions — check the
  extraction script's docstring if unsure which is current.

## Key methodology notes and assumptions

Please read before relying on any of this for client-facing output — several of these are
judgement calls, not settled facts.

- **Cash uses the real Bank of England SONIA rate**, not the Bloomberg file's own cash column
  (which produced nonsensical ±100-300% monthly swings). Built from BoE's IUDSOIA series
  (2014+), spliced with the Blackrock ICS Sterling Liquidity Fund series pre-2014 (99.7%
  correlated over the overlap period) — see `build_sonia_cash.py`.
- **Every holding maps to a broad asset-class index**, not its own fund-level history — most
  individual fund series in the source data are too short (some ~20 months) for a 25+ year
  Monte Carlo. See `portfolios.py` for the exact mapping.
- **"Original" vs "Alternative" is mainly a fee story** — the source data shows these largely
  hold the *same* underlying index exposure; the difference being compared is cost, not
  market return.
- **"Better" portfolio weights were tuned empirically**, not derived from a single source of
  truth — REITs/Infrastructure in this data run ~0.75-0.76 correlated with global equities,
  so they diversify less than their labels suggest; real diversification comes mostly from
  bonds/credit. One reasonable construction, not the only one — sanity-check before relying
  on it.
- **Guardrails are typically a bigger lever on ruin probability than portfolio choice** —
  worth leading with in any client narrative.
- **Mortality** uses the S4 pension-scheme table (lighter than general-population tables, the
  standard choice for pension decumulation work), assumes independence from market returns,
  and — for joint life — independence between the two lives of a couple (a known
  simplification; real couples' deaths correlate somewhat via shared lifestyle factors).
- **Tax + State Pension** modelling is deliberately simplified: whole pot treated as a single
  taxable pension wrapper (no 25% pension-commencement lump sum, no ISA/GIA wrapper split),
  rest-of-UK tax bands only, both held in today's money for the whole horizon. State Pension
  defaults to the full new State Pension — a real client's entitlement varies by NI record.
- **Historical window is short** (1999/2000-2026, ~26 years) relative to a 30-year
  decumulation horizon, and happens to span an unusually strong run for global equities —
  treat any bootstrap of this window as illustrative, not predictive.
- **Forward-looking CMA figures** are a compiled median across third-party published
  forecasts (via Monevator: Vanguard/Schroders/JPMorgan/BlackRock etc.), not an in-house
  view. Three asset classes have no direct published match and are proxied from the closest
  category — see `cma.py`.
- **Annuity rates** are scaled examples from Hargreaves Lansdown's published best-buy table
  (May 2026), not a personalised quote — real quotes vary by provider, postcode and health.

## Known gaps / where things were left off

- **7 of the fund store's asset-class sub-categories have no return data at all**: LDI, Multi
  Asset, Multi Asset Credit, Private Credit, Private Equity, Private Markets Multi Asset, Real
  Assets. The Portfolio Builder Game shows these as "coming soon" rather than faking numbers
  for them — see `FUND_STORE_MAP` in `app/pages/1_Portfolio_Builder_Game.py`. Ben (colleague)
  was asked which specific fund to use as the representative for each fund-store section,
  including these — **check whether that reply has come in**, then add the return series to
  `data/asset_class_returns.csv` + a row to `data/asset_class_map.csv`; no other code changes
  needed once the data exists.
- **Portfolio Builder Game leaderboard is a CSV file on Streamlit Cloud's ephemeral disk**
  (`game_state/leaderboard.csv`) — fine for a single live session, but it (a) resets on every
  app restart/redeploy, and (b) can silently lose entries under genuinely simultaneous
  submissions (naive read-modify-write, no locking). If this becomes a recurring or
  high-traffic company-wide thing rather than a one-off, replace this with a real shared
  store (a Google Sheet via `gspread`, or a small hosted DB) before relying on it.
- **Individual UK equities work (internship Weeks 5-8)** is a separate, less mature thread
  from the main simulator — `equity_income.py` + the AQR/RAISE swap tests are real, working
  code, but this hasn't been folded into the main app's UI at all; it's currently
  script/notebook-style analysis only.
- **Portability gotcha**: `app/pages/1_Portfolio_Builder_Game.py` briefly broke the entire
  deployed app (not just that page) because a module-level type annotation used PEP 604/585
  syntax (`dict[str, list[str] | None]`) that needs Python 3.10+, and Streamlit Cloud's exact
  Python version wasn't confirmed. Fixed with `from __future__ import annotations` at the top
  of that file. **If you add a new page to `app/pages/`, either add that same import or avoid
  bleeding-edge type-hint syntax** — Streamlit appears to touch every page file when building
  the sidebar nav, so a syntax/import error in ANY page can crash the whole app, not just that
  page.
- **No automated test suite.** Every module is independently runnable for a manual self-test
  (`python src/tax.py` etc.), and there's a handful of verification scripts
  (`verify_cma_annuity.py`), but there's no `pytest` suite — worth adding if this becomes a
  longer-term maintained product rather than an internship deliverable.

## Deployment

Streamlit Community Cloud, connected to this repo's `master` branch — **any push to `master`
auto-redeploys within roughly a minute**. No manual deploy step. If the deployed app shows
"Oh no. Error running app.":

1. Go to [share.streamlit.io](https://share.streamlit.io), sign in, find this app in the
   dashboard (not the public app URL — the "Manage app" button on a crashed app page is
   unreliable).
2. Open its management page — there's a terminal/log panel showing the real Python traceback.
3. A crashed app sometimes needs a manual **Reboot** even after the underlying bug is fixed
   and pushed — it doesn't always retry automatically.

## Suggested next steps

- Get Ben's fund picks for the 7 missing asset-class sub-categories and wire them in (see
  [Known gaps](#known-gaps--where-things-were-left-off)).
- Confirm the Original-portfolio OCF assumptions against real fund factsheets.
- Sanity-check / adjust the "Better" portfolio weights with the team.
- Tax refinements: 25% pension-commencement lump sum, real ISA/GIA wrapper split, let the
  client enter their own State Pension forecast, consider Scottish tax bands.
- Annuity refinements: 25% lump sum before annuitizing, a fuller joint-life rate curve,
  enhanced/impaired-life rates.
- Fold the individual UK equities work (Weeks 5-8) into the main app's UI, if that thread is
  continuing.
- If the Portfolio Builder Game becomes a recurring company-wide activity, replace its CSV
  leaderboard with a real shared store (see [Known gaps](#known-gaps--where-things-were-left-off)).
- Turn this from an internship deliverable into a scalable practice-management product:
  branded client-facing reports generated straight from a saved scenario, a "batch mode" to
  re-run a whole book of clients against updated market data, a live FNZ data feed instead of
  a point-in-time Bloomberg pull, and an audit trail of what assumptions were live when a
  piece of advice was given (useful for Consumer Duty record-keeping).
