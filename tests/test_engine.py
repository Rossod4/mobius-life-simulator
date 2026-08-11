"""
Smoke tests for src/engine.py - the actual probability-of-ruin math behind both the main
comparison app and the Portfolio Builder Game. These aren't exhaustive; the goal is to catch a
future edit that silently breaks the simulation (wrong shapes, NaNs, an impossible probability)
before it reaches a live audience, not to validate every statistical property of the model.

Run with: pytest tests/ (from the repo root, after `pip install -r requirements-dev.txt`)
"""
import numpy as np
import pandas as pd
import pytest

from engine import load_asset_returns, load_cpi, run_simulation, ClientProfile
from portfolios import PORTFOLIOS


@pytest.fixture(scope="module")
def asset_df():
    return load_asset_returns()


@pytest.fixture(scope="module")
def cpi(asset_df):
    return load_cpi(asset_df)


@pytest.fixture
def profile():
    return ClientProfile(starting_age=65, horizon_years=30, starting_pot=500_000, initial_annual_spend=20_000)


def test_data_loads_and_is_non_trivial(asset_df, cpi):
    assert len(asset_df) > 100, "expected many months of history, something's wrong with the data load"
    assert len(cpi) > 100
    assert asset_df.index.is_monotonic_increasing


def test_named_portfolios_all_simulate_without_error(asset_df, cpi, profile):
    """Every registered portfolio (data/portfolio_holdings.csv) should run end to end and produce a
    sane probability of ruin - this is the single test most likely to catch a broken data edit
    (a portfolio's holdings pointing at a missing/renamed asset class, weights not summing right,
    etc.) before it reaches the live app."""
    for name in PORTFOLIOS:
        result = run_simulation(name, asset_df, cpi, profile, method="stationary_block",
                                 n_sims=500, seed=1)
        assert 0.0 <= result.prob_ruin <= 1.0, f"{name}: prob_ruin out of range: {result.prob_ruin}"
        assert not np.isnan(result.paths).any(), f"{name}: NaN in simulated paths"
        assert (result.paths >= 0).all(), f"{name}: pot went negative for {name}"


def test_run_simulation_output_shapes(asset_df, cpi, profile):
    n_sims = 300
    result = run_simulation("Better", asset_df, cpi, profile, method="stationary_block",
                             n_sims=n_sims, seed=1)
    assert result.paths.shape == (n_sims, profile.horizon_years + 1)
    assert result.spend_paths.shape == (n_sims, profile.horizon_years)
    assert result.ruin_year.shape == (n_sims,)
    assert result.paths[:, 0].tolist() == [profile.starting_pot] * n_sims, \
        "every path should start at the client's actual starting pot"


def test_same_seed_is_fully_reproducible(asset_df, cpi, profile):
    """The game relies on this: every "reveal" and every crash-scenario click uses a fixed seed, so
    a player re-triggering the same computation (e.g. a rerun) must get bit-identical numbers, not
    a different roll of the dice."""
    r1 = run_simulation("Better", asset_df, cpi, profile, method="stationary_block", n_sims=200, seed=7)
    r2 = run_simulation("Better", asset_df, cpi, profile, method="stationary_block", n_sims=200, seed=7)
    np.testing.assert_array_equal(r1.paths, r2.paths)
    assert r1.prob_ruin == r2.prob_ruin


def test_custom_weights_override_named_portfolio(asset_df, cpi, profile):
    """custom_weights/custom_fee is exactly what the game uses for a player's own allocation - this
    confirms the override path actually changes the result rather than silently falling back to
    the named portfolio's own weights."""
    named = run_simulation("Better", asset_df, cpi, profile, method="stationary_block", n_sims=300, seed=3)
    custom_weights = pd.Series({"Global Equities": 1.0})
    custom = run_simulation("Better", asset_df, cpi, profile, method="stationary_block",
                             n_sims=300, seed=3, custom_weights=custom_weights, custom_fee=0.001)
    assert not np.array_equal(named.paths, custom.paths), \
        "100% equity custom weights produced identical paths to Better - override isn't taking effect"


def test_higher_equity_weight_increases_spread(asset_df, cpi, profile):
    """A directional sanity check, not a precise statistical claim: an all-equity portfolio should
    show a materially WIDER spread of outcomes than an all-gilts portfolio, given the same
    spend/horizon - comparing standard deviation of the final pot rather than a low percentile,
    since at a 30-year horizon both portfolios ruin often enough that their 5th-percentile legacy
    floors at exactly £0 (a tie, not a meaningful comparison). If this spread relationship ever
    flips, something fundamental broke (e.g. a sign error, a units mix-up in
    weighted_monthly_returns)."""
    all_equity = run_simulation("Custom", asset_df, cpi, profile, method="stationary_block",
                                 n_sims=1000, seed=42,
                                 custom_weights=pd.Series({"Global Equities": 1.0}), custom_fee=0.001)
    all_gilts = run_simulation("Custom", asset_df, cpi, profile, method="stationary_block",
                                n_sims=1000, seed=42,
                                custom_weights=pd.Series({"UK Gilts All Stocks": 1.0}), custom_fee=0.001)
    assert all_equity.legacy.std() > all_gilts.legacy.std()


def test_prob_ruin_confidence_interval_is_sane(asset_df, cpi, profile):
    result = run_simulation("Better", asset_df, cpi, profile, method="stationary_block", n_sims=500, seed=9)
    lo, hi = result.prob_ruin_ci()
    assert 0.0 <= lo <= result.prob_ruin <= hi <= 1.0


def test_zero_spend_never_ruins(asset_df, cpi):
    """Degenerate case: a client who spends nothing should never run out of money, regardless of
    market path - a useful edge-case check that ruin logic isn't off-by-one or inverted."""
    profile = ClientProfile(starting_age=65, horizon_years=20, starting_pot=500_000, initial_annual_spend=0.0)
    result = run_simulation("Better", asset_df, cpi, profile, method="stationary_block", n_sims=300, seed=5)
    assert result.prob_ruin == 0.0
