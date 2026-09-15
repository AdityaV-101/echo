import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

EVAL_DIR = Path(__file__).parent.parent / "eval"
REPO_ROOT = Path(__file__).parent.parent
