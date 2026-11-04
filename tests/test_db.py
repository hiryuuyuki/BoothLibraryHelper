# tests/test_db.py
# ============================================
# BoothLibraryHelper
# db.DB の現状挙動を固定する（特性テスト）
# ============================================
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.db import DB, compute_hash
from app.models import BoothItem


class DBTestCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.db = DB(Path(self._td.name) / "test.db")

    def tearDown(self):
        self.db.conn.close()
        self._td.cleanup()


class TestComputeHash(unittest.TestCase):
    def test_deterministic_and_sensitive(self):
        a = compute_hash("t", "u", "th")
        self.assertEqual(a, compute_hash("t", "u", "th"))
        self.assertNotEqual(a, compute_hash("t2", "u", "th"))
        self.assertNotEqual(a, compute_hash("t", "u", None))


class TestUpsert(DBTestCase):
    def test_first_insert_is_not_update(self):
        self.assertEqual(self.db.upsert_item("1", "A", "u", "th", "/f"), 0)

    def test_same_content_is_not_update(self):
        self.db.upsert_item("1", "A", "u", "th", "/f")
        self.assertEqual(self.db.upsert_item("1", "A", "u", "th", "/f"), 0)

    def test_changed_content_is_update(self):
        self.db.upsert_item("1", "A", "u", "th", "/f")
        self.assertEqual(self.db.upsert_item("1", "A (v2)", "u", "th", "/f"), 1)

    def test_folder_change_alone_is_not_update(self):
        self.db.upsert_item("1", "A", "u", "th", "/f")
        self.assertEqual(self.db.upsert_item("1", "A", "u", "th", "/moved"), 0)

    def test_upsert_does_not_duplicate_rows(self):
        self.db.upsert_item("1", "A", "u", "th", "/f")
        self.db.upsert_item("1", "B", "u", "th", "/f")
        self.assertEqual(len(self.db.list_items()), 1)

    def test_clear_update_flag(self):
        self.db.upsert_item("1", "A", "u", "th", "/f")
        self.db.upsert_item("1", "B", "u", "th", "/f")
        self.db.clear_update_flag("1")
        row = self.db.conn.execute("SELECT has_update FROM items WHERE item_id='1'").fetchone()
        self.assertEqual(row[0], 0)


class TestListItems(DBTestCase):
    def test_maps_rows_to_boothitem(self):
        self.db.upsert_item("42", "商品名", "https://booth.pm/ja/items/42", None, Path("/dl/[42] 商品名"))
        items = self.db.list_items()
        self.assertEqual(len(items), 1)
        bi = items[0]
        self.assertIsInstance(bi, BoothItem)
        self.assertEqual(bi.item_id, "42")
        self.assertEqual(bi.name, "商品名")
        self.assertEqual(bi.url, "https://booth.pm/ja/items/42")
        self.assertIsNone(bi.thumbnail_url)
        self.assertEqual(bi.folder, str(Path("/dl/[42] 商品名")))
        # last_seen_ts を UTC ISO8601 + "Z" に変換
        self.assertTrue(bi.updated_at.endswith("Z"))

    def test_ordered_by_last_seen_desc(self):
        with mock.patch("app.db.time.time", return_value=1000):
            self.db.upsert_item("old", "O", "u", None, "/f")
        with mock.patch("app.db.time.time", return_value=2000):
            self.db.upsert_item("new", "N", "u", None, "/f")
        self.assertEqual([i.item_id for i in self.db.list_items()], ["new", "old"])

    def test_updated_at_value(self):
        with mock.patch("app.db.time.time", return_value=0):
            self.db.upsert_item("1", "A", "u", None, "/f")
        self.assertEqual(self.db.list_items()[0].updated_at, "1970-01-01T00:00:00Z")

    def test_empty_db(self):
        self.assertEqual(self.db.list_items(), [])

    def test_reopen_keeps_data(self):
        path = Path(self._td.name) / "test.db"
        self.db.upsert_item("1", "A", "u", None, "/f")
        self.db.conn.close()
        self.db = DB(path)
        self.assertEqual(len(self.db.list_items()), 1)


if __name__ == "__main__":
    unittest.main()
