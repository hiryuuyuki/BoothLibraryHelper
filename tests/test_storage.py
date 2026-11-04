# tests/test_storage.py
# ============================================
# BoothLibraryHelper
# storage.scan_dl_folder の現状挙動を固定する（特性テスト）
# 通信関数はすべてモックに差し替え、ネットワークには接続しない
# ============================================
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import storage, utils


def _make_tree(root: Path):
    a = root / "[100] 商品A"
    a.mkdir()
    (a / "a.zip").write_bytes(b"")
    (a / "readme.txt").write_bytes(b"")
    b = root / "手動フォルダ"  # 商品IDなし
    b.mkdir()
    (b / "x.psd").write_bytes(b"")
    (root / "loose.zip").write_bytes(b"")  # 直下のファイルは対象外


class TestScanDlFolder(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        _make_tree(self.root)
        self.thumb = mock.patch.object(
            storage,
            "fetch_and_cache_thumbnail",
            return_value=(
                ".thumbnail_cache/booth.jpg",
                {"official_title": "公式タイトル", "product_url": "https://booth.pm/ja/items/100"},
            ),
        )
        self.meta = mock.patch.object(storage, "fetch_public_item_meta", return_value=None)
        self.mock_thumb = self.thumb.start()
        self.mock_meta = self.meta.start()

    def tearDown(self):
        self.thumb.stop()
        self.meta.stop()
        self._td.cleanup()

    def _by_title(self, items):
        return {i["title"]: i for i in items}

    def test_returns_list_of_item_dicts(self):
        # 直近コミットで summary dict -> list に変更された契約
        items = storage.scan_dl_folder(str(self.root))
        self.assertIsInstance(items, list)
        self.assertEqual(sorted(self._by_title(items)), ["[100] 商品A", "手動フォルダ"])

    def test_item_with_product_id(self):
        it = self._by_title(storage.scan_dl_folder(str(self.root)))["[100] 商品A"]
        self.assertEqual(it["product_id"], "100")
        self.assertEqual(it["product_url"], "https://booth.pm/ja/items/100")
        self.assertEqual(it["official_title"], "公式タイトル")
        self.assertEqual(it["thumbnail"], ".thumbnail_cache/booth.jpg")
        self.assertEqual(it["path"], os.path.join(str(self.root), "[100] 商品A"))

    def test_ui_compat_top_level_counts(self):
        it = self._by_title(storage.scan_dl_folder(str(self.root)))["[100] 商品A"]
        self.assertEqual(it["zip_count"], 1)
        self.assertEqual(it["doc_count"], 1)
        self.assertEqual(it["source_count"], 0)
        self.assertEqual(it["image_count"], 0)
        self.assertEqual(it["stats"]["archive_count"], it["zip_count"])

    def test_item_without_product_id_does_not_fetch(self):
        it = self._by_title(storage.scan_dl_folder(str(self.root)))["手動フォルダ"]
        self.assertEqual(it["product_id"], "")
        self.assertEqual(it["thumbnail"], "")
        self.assertEqual(it["source_count"], 1)
        # 通信系はID付きフォルダの1回だけ
        self.assertEqual(self.mock_thumb.call_count, 1)

    def test_writes_metadata_json(self):
        items = storage.scan_dl_folder(str(self.root))
        self.assertEqual(utils.read_metadata_json(str(self.root)), {"items": items})

    def test_keeps_purchase_info_from_previous_scan(self):
        first = storage.scan_dl_folder(str(self.root))
        for it in first:
            if it["product_id"] == "100":
                it["purchase_title"] = "  購入時タイトル  "
                it["purchased_at"] = "2026-01-01"
        utils.write_metadata_json(str(self.root), first)

        it = self._by_title(storage.scan_dl_folder(str(self.root)))["[100] 商品A"]
        self.assertEqual(it["purchase_title"], "購入時タイトル")
        self.assertEqual(it["purchased_at"], "2026-01-01")

    def test_fallback_to_previous_thumbnail_when_fetch_fails(self):
        storage.scan_dl_folder(str(self.root))
        self.mock_thumb.return_value = ("", None)
        it = self._by_title(storage.scan_dl_folder(str(self.root)))["[100] 商品A"]
        self.assertEqual(it["thumbnail"], ".thumbnail_cache/booth.jpg")

    def test_fetch_exception_does_not_abort_scan(self):
        self.mock_thumb.side_effect = RuntimeError("network down")
        items = storage.scan_dl_folder(str(self.root))
        self.assertEqual(len(items), 2)


if __name__ == "__main__":
    unittest.main()
