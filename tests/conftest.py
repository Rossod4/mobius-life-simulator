"""
Puts src/ on sys.path the same way every app entry point does (see app/app.py, engine.py's own
sibling imports of portfolios/tax/mortality) - the codebase uses flat same-directory imports
throughout rather than a package structure, so tests need the same path setup to import them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
