# tests/test_settings.py
# ============================================
# BoothLibraryHelper
# settings.py の現状挙動を固定する（特性テスト）
# 実ファイル（リポジトリ直下 settings.json）には触れず、SETTINGS_PATH を一時パスに差し替える
# ============================================
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import settings


class SettingsTestCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.path = self.tmp / "settings.json"
        self._patch = mock.patch.object(settings, "SETTINGS_PATH", self.path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._td.cleanup()


class TestLoadSave(SettingsTestCase):
    def test_missing_file_returns_empty(self):
        self.assertEqual(settings.load_settings(), {})

    def test_roundtrip(self):
        settings.save_settings({"a": 1, "名前": "値"})
        self.assertEqual(settings.load_settings(), {"a": 1, "名前": "値"})

    def test_utf8_bom_is_accepted(self):
        self.path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"k": "v"}).encode("utf-8"))
        self.assertEqual(settings.load_settings(), {"k": "v"})

    def test_broken_json_returns_empty(self):
        self.path.write_text("{broken", encoding="utf-8")
        self.assertEqual(settings.load_settings(), {})

    def test_non_dict_json_returns_empty(self):
        self.path.write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(settings.load_settings(), {})


class TestLastDlFolder(SettingsTestCase):
    def test_set_and_get_existing_folder(self):
        target = self.tmp / "DL フォルダ"
        target.mkdir()
        settings.set_last_dl_folder(str(target))
        got = settings.get_last_dl_folder()
        self.assertEqual(got, os.path.normpath(str(target.resolve())))
        saved = settings.load_settings()
        self.assertTrue(saved["last_dl_folder_updated_at"].endswith("Z"))

    def test_nonexistent_path_is_not_stored(self):
        settings.set_last_dl_folder(str(self.tmp / "nope"))
        self.assertNotIn("last_dl_folder", settings.load_settings())

    def test_get_returns_none_when_folder_was_deleted(self):
        target = self.tmp / "gone"
        target.mkdir()
        settings.set_last_dl_folder(str(target))
        target.rmdir()
        self.assertIsNone(settings.get_last_dl_folder())

    def test_get_ignores_blank_or_non_string(self):
        settings.save_settings({"last_dl_folder": "   "})
        self.assertIsNone(settings.get_last_dl_folder())
        settings.save_settings({"last_dl_folder": 123})
        self.assertIsNone(settings.get_last_dl_folder())


class TestUiState(SettingsTestCase):
    def test_default_empty(self):
        self.assertEqual(settings.get_ui_state(), {})

    def test_set_and_get(self):
        settings.set_ui_state({"sort": "name"})
        self.assertEqual(settings.get_ui_state(), {"sort": "name"})

    def test_non_dict_is_ignored(self):
        settings.set_ui_state({"sort": "name"})
        settings.set_ui_state(["bad"])
        self.assertEqual(settings.get_ui_state(), {"sort": "name"})

    def test_set_ui_state_keeps_other_keys(self):
        settings.save_settings({"last_dl_folder": "x"})
        settings.set_ui_state({"a": 1})
        self.assertEqual(settings.load_settings()["last_dl_folder"], "x")


if __name__ == "__main__":
    unittest.main()
