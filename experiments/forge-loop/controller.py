"""Compatibility import; the maintained non-financial controller lives in scripts/."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from forge_loop import *
