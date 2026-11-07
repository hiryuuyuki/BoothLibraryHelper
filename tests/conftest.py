# tests/conftest.py
# ============================================
# BoothLibraryHelper
# pytest 共通設定：リポジトリ直下を import パスに追加し、`import app.xxx` を可能にする
# ============================================
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
