# app/models.py
# ============================================
# BoothLibraryHelper
# データモデル定義
# ============================================

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict
import json
import hashlib


@dataclass
class BoothItem:
    """
    Booth 購入商品の正規データモデル
    """

    item_id: str                 # 管理ID（Booth内部ID or URL由来）
    name: str                    # 商品名
    url: str                     # Booth 商品ページURL
    thumbnail_url: Optional[str] # サムネイルURL
    folder: Optional[str]        # ローカル保存フォルダ
    updated_at: Optional[str]    # 更新日時（取得できる場合）

    # ----------------------------------------
    # dict 変換
    # ----------------------------------------
    def to_dict(self) -> Dict:
        return asdict(self)

    # ----------------------------------------
    # JSON 保存
    # ----------------------------------------
    def save_metadata(self, folder: Path):
        """
        metadata.json を保存
        """
        folder.mkdir(parents=True, exist_ok=True)
        meta_path = folder / "metadata.json"
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    # ----------------------------------------
    # JSON 読み込み
    # ----------------------------------------
    @staticmethod
    def load_metadata(path: Path) -> "BoothItem":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return BoothItem(**data)

    # ----------------------------------------
    # 差分検知用ハッシュ
    # ----------------------------------------
    def fingerprint(self) -> str:
        """
        差分検知用のフィンガープリント生成
        """
        src = f"{self.name}|{self.url}|{self.thumbnail_url}|{self.updated_at}"
        return hashlib.sha256(src.encode("utf-8")).hexdigest()
