# tests/test_models.py
# ============================================
# BoothLibraryHelper
# models.BoothItem の現状挙動を固定する（特性テスト）
# ============================================
import json
import tempfile
import unittest
from pathlib import Path

from app.models import BoothItem


def _item(**kw):
    base = dict(
        item_id="123456",
        name="テスト衣装【VRChat想定】",
        url="https://booth.pm/ja/items/123456",
        thumbnail_url="https://example.invalid/t.jpg",
        folder="C:/BOOTH/[123456] テスト衣装",
        updated_at="2026-01-01T00:00:00Z",
    )
    base.update(kw)
    return BoothItem(**base)


class TestBoothItem(unittest.TestCase):
    def test_to_dict_has_all_fields(self):
        d = _item().to_dict()
        self.assertEqual(
            set(d), {"item_id", "name", "url", "thumbnail_url", "folder", "updated_at"}
        )

    def test_save_and_load_roundtrip_keeps_japanese(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "nested" / "dir"
            src = _item()
            src.save_metadata(folder)

            meta_path = folder / "metadata.json"
            self.assertTrue(meta_path.exists())
            # ensure_ascii=False で日本語がそのまま書かれる
            self.assertIn("テスト衣装", meta_path.read_text(encoding="utf-8"))

            loaded = BoothItem.load_metadata(meta_path)
            self.assertEqual(loaded, src)

    def test_optional_fields_accept_none(self):
        with tempfile.TemporaryDirectory() as td:
            src = _item(thumbnail_url=None, folder=None, updated_at=None)
            src.save_metadata(Path(td))
            loaded = BoothItem.load_metadata(Path(td) / "metadata.json")
            self.assertIsNone(loaded.thumbnail_url)
            self.assertEqual(loaded, src)

    def test_load_rejects_unknown_keys(self):
        # 現状: 余分なキーがあると TypeError（BoothItem(**data) のため）
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "metadata.json"
            data = _item().to_dict()
            data["extra"] = 1
            p.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(TypeError):
                BoothItem.load_metadata(p)


class TestFingerprint(unittest.TestCase):
    def test_stable_for_same_content(self):
        self.assertEqual(_item().fingerprint(), _item().fingerprint())

    def test_changes_when_tracked_field_changes(self):
        base = _item().fingerprint()
        self.assertNotEqual(base, _item(name="別名").fingerprint())
        self.assertNotEqual(base, _item(url="https://booth.pm/ja/items/1").fingerprint())
        self.assertNotEqual(base, _item(thumbnail_url=None).fingerprint())
        self.assertNotEqual(base, _item(updated_at="2027-01-01T00:00:00Z").fingerprint())

    def test_ignores_folder_and_item_id(self):
        base = _item().fingerprint()
        self.assertEqual(base, _item(folder="D:/other").fingerprint())
        self.assertEqual(base, _item(item_id="999").fingerprint())

    def test_is_sha256_hex(self):
        fp = _item().fingerprint()
        self.assertEqual(len(fp), 64)
        int(fp, 16)


if __name__ == "__main__":
    unittest.main()
