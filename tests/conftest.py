# tests/conftest.py
import sys
from pathlib import Path

# pridaj koreň repozitára na import path, aby `import src...` fungoval aj v CI
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
