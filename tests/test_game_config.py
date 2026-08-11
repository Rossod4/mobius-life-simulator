"""
Smoke tests for the static config dicts in app/pages/1_Portfolio_Builder_Game.py (FUND_STORE_MAP,
ASSET_CLASS_INFO) - the game's own asset-class list and the hints/cheat-sheet content added
alongside it. These would be the easiest thing to quietly break while adding a new fund-store
category or asset class (e.g. adding a FUND_STORE_MAP entry but forgetting its ASSET_CLASS_INFO
blurb, so a slider's "i" tooltip silently goes missing).

The game file is a Streamlit PAGE script (executes top-level UI code on import, e.g. st.markdown()
calls that need a real Streamlit runtime) - rather than importing it directly, its config dicts are
extracted via ast.literal_eval, exactly the way this was checked by hand while building the hints
feature. This is deliberately read-only static analysis, not a run of the actual page.

Run with: pytest tests/ (from the repo root, after `pip install -r requirements-dev.txt`)
"""
import ast
from pathlib import Path

import pytest

from portfolios import AC

GAME_FILE = Path(__file__).resolve().parent.parent / "app" / "pages" / "1_Portfolio_Builder_Game.py"


def _extract_module_level_dict(tree: ast.Module, name: str) -> dict:
    for node in tree.body:
        target = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        if target == name and node.value is not None:
            return ast.literal_eval(node.value)
    raise AssertionError(f"module-level dict {name!r} not found in {GAME_FILE.name}")


@pytest.fixture(scope="module")
def game_tree():
    return ast.parse(GAME_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fund_store_map(game_tree):
    return _extract_module_level_dict(game_tree, "FUND_STORE_MAP")


@pytest.fixture(scope="module")
def asset_class_info(game_tree):
    return _extract_module_level_dict(game_tree, "ASSET_CLASS_INFO")


def test_fund_store_map_constituents_have_real_return_data(fund_store_map):
    """A category mapped to a list (not None) claims those underlying labels are playable in the
    game - each one must actually have a return series behind it (AC, from asset_class_map.csv),
    or a player's build would crash on reveal."""
    for category, constituents in fund_store_map.items():
        if constituents is None:
            continue
        for label in constituents:
            assert label in AC, f"{category!r} maps to {label!r}, which has no entry in asset_class_map.csv"


def test_every_fund_store_category_has_a_hint(fund_store_map, asset_class_info):
    missing = [c for c in fund_store_map if c not in asset_class_info]
    assert not missing, f"fund-store categories missing an ASSET_CLASS_INFO hint: {missing}"


def test_every_individual_building_block_has_a_hint(asset_class_info):
    missing = [label for label in AC if label not in asset_class_info]
    assert not missing, f"individual building blocks missing an ASSET_CLASS_INFO hint: {missing}"


def test_asset_class_info_entries_are_well_formed(asset_class_info):
    """Each entry is (blurb, risk_tier) where risk_tier starts with one of the three traffic-light
    emoji the slider tooltips and cheat sheet rely on - a typo here (e.g. a plain string tier)
    would silently break the risk-tier colour coding used by the live risk dial too."""
    valid_tiers = ("🟢", "🟡", "🔴")
    for label, info in asset_class_info.items():
        assert isinstance(info, tuple) and len(info) == 2, f"{label!r}: expected (blurb, risk_tier) tuple"
        blurb, risk_tier = info
        assert isinstance(blurb, str) and len(blurb) > 10, f"{label!r}: blurb looks too short/missing"
        assert risk_tier.startswith(valid_tiers), f"{label!r}: risk tier {risk_tier!r} doesn't start with 🟢/🟡/🔴"
