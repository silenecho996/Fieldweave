"""Shared test paths: put src/ on sys.path before importing project modules."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

KNOWLEDGE_DB = ROOT / "data" / "knowledge-base.sqlite3"
WORKSPACE_DB = ROOT / "data" / "workspace.sqlite3"
