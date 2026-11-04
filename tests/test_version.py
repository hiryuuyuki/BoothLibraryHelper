# tests/test_version.py
# ============================================
# BoothLibraryHelper
# version.py の現状挙動を固定する（特性テスト）
# ============================================
import unittest

from app import version


class TestVersionConstants(unittest.TestCase):
    def test_aliases_point_to_app_version(self):
        # 直近コミットで追加された互換別名が壊れないこと
        self.assertEqual(version.VERSION, version.APP_VERSION)
        self.assertEqual(version.APP_TITLE, f"{version.APP_NAME} v{version.APP_VERSION}")
        self.assertEqual(version.DISPLAY_VERSION, version.APP_TITLE)

    def test_app_version_is_semver_triplet(self):
        parts = version.APP_VERSION.split(".")
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(p.isdigit() for p in parts))

    def test_auto_update_disabled(self):
        # 規約配慮で自動更新は無効のまま
        self.assertFalse(version.UPDATE_INFO["enabled"])
        self.assertIsNone(version.UPDATE_INFO["check_url"])


class TestIsNewer(unittest.TestCase):
    def test_newer_patch_minor_major(self):
        self.assertTrue(version.is_newer("0.9.0", "0.9.1"))
        self.assertTrue(version.is_newer("0.9.0", "0.10.0"))
        self.assertTrue(version.is_newer("0.9.0", "1.0.0"))

    def test_same_or_older_is_not_newer(self):
        self.assertFalse(version.is_newer("0.9.0", "0.9.0"))
        self.assertFalse(version.is_newer("0.9.1", "0.9.0"))

    def test_numeric_not_lexicographic(self):
        # "10" > "9" を数値として比較すること
        self.assertTrue(version.is_newer("0.9.0", "0.10.0"))
        self.assertFalse(version.is_newer("0.10.0", "0.9.0"))


if __name__ == "__main__":
    unittest.main()
