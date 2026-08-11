"""
Smoke tests for src/portfolios.py - the data-driven portfolio loading that both the main app and
the game rely on. These exist to catch a bad data edit (weights that don't sum to 1, a fat-
fingered fee, a missing asset-class mapping) before it silently produces wrong probability-of-ruin
numbers in front of a live audience.

Run with: pytest tests/ (from the repo root, after `pip install -r requirements-dev.txt`)
"""
import pytest

from portfolios import (
    PORTFOLIOS, AC, EQUITY_CLASSES, asset_class_weights, weighted_avg_fee,
    scale_to_equity_weight, load_comparison_groups,
)


def test_portfolios_load_and_include_the_expected_core_set():
    assert len(PORTFOLIOS) > 0
    # These four are referenced by name throughout the app/game - if any of them go missing (e.g.
    # a rename in portfolio_holdings.csv) a lot of the UI breaks, not just this test.
    for expected in ("Original", "Better"):
        assert expected in PORTFOLIOS, f"expected portfolio {expected!r} missing from PORTFOLIOS"


@pytest.mark.parametrize("name", list(PORTFOLIOS.keys()))
def test_asset_class_weights_sum_to_one(name):
    """The single most important data invariant in the whole model: if a portfolio's weights don't
    sum to ~1.0, every downstream probability-of-ruin figure for it is meaningless."""
    total = asset_class_weights(name).sum()
    assert total == pytest.approx(1.0, abs=0.01), f"{name}: weights sum to {total}, not 1.0"


@pytest.mark.parametrize("name", list(PORTFOLIOS.keys()))
def test_weighted_avg_fee_is_a_plausible_percentage(name):
    """Fees are stored as decimals (0.007 = 0.7% pa) - this catches a fee fat-fingered in as a
    whole percentage point (e.g. 0.7 instead of 0.007), which would silently wreck every
    simulation's net returns for that portfolio."""
    fee = weighted_avg_fee(name)
    assert 0.0 <= fee < 0.05, f"{name}: weighted-avg fee {fee} looks implausible (expected < 5% pa)"


@pytest.mark.parametrize("name", list(PORTFOLIOS.keys()))
def test_every_holding_asset_class_is_mapped(name):
    """Every AssetClass a portfolio's holdings reference must have a return series behind it (via
    AC, the Label -> Bloomberg column map) - an unmapped asset class fails loudly inside
    run_simulation with a KeyError; better to catch it here with a clear message."""
    weights = asset_class_weights(name)
    for asset_class in weights.index:
        assert asset_class in AC, f"{name}: asset class {asset_class!r} has no entry in asset_class_map.csv"


@pytest.mark.parametrize("target", [0.0, 0.2, 0.5, 0.8, 1.0])
def test_scale_to_equity_weight_hits_target(target):
    scaled = scale_to_equity_weight("Better", target)
    assert scaled.sum() == pytest.approx(1.0, abs=0.01)
    actual_equity = scaled[scaled.index.isin(EQUITY_CLASSES)].sum()
    assert actual_equity == pytest.approx(target, abs=0.01)


def test_comparison_groups_load():
    groups = load_comparison_groups()
    assert len(groups) > 0
