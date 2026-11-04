# tests/test_utils.py
# ============================================
# BoothLibraryHelper
# utils.py のうち通信しない関数の現状挙動を固定する（特性テスト）
# ============================================
import os
import tempfile
import unittest
from pathlib import Path

from app import utils


class TestProductId(unittest.TestCase):
    def test_extract_from_folder_name(self):
        self.assertEqual(utils.extract_product_id("[123456] 商品名"), "123456")

    def test_no_bracket_prefix_returns_none(self):
        self.assertIsNone(utils.extract_product_id("商品名 [123456]"))
        self.assertIsNone(utils.extract_product_id("123456 商品名"))
        self.assertIsNone(utils.extract_product_id("[abc] 商品名"))
        self.assertIsNone(utils.extract_product_id(""))

    def test_build_public_url(self):
        self.assertEqual(utils.build_public_item_url("42"), "https://booth.pm/ja/items/42")


class TestNormalizeItemUrl(unittest.TestCase):
    def test_variants_normalize_to_public_url(self):
        want = "https://booth.pm/ja/items/42"
        for src in [
            "https://booth.pm/ja/items/42",
            "https://shop.booth.pm/items/42",
            "http://booth.pm/en/items/42?x=1",
            "//booth.pm/ja/items/42",
            "/ja/items/42",
            "  https://booth.pm/ja/items/42  ",
        ]:
            with self.subTest(src=src):
                self.assertEqual(utils._normalize_item_url(src), want)

    def test_invalid_inputs(self):
        for src in [None, "", "   ", "booth.pm/ja/items/42", "https://booth.pm/ja/items/", 42]:
            with self.subTest(src=src):
                self.assertIsNone(utils._normalize_item_url(src))


class TestExtractUrls(unittest.TestCase):
    def test_from_text_one_per_line(self):
        text = "https://booth.pm/ja/items/1\n\nnot a url\n  https://a.booth.pm/items/2  \n"
        self.assertEqual(
            utils._extract_urls_from_text(text),
            ["https://booth.pm/ja/items/1", "https://booth.pm/ja/items/2"],
        )

    def test_from_html_anchor_with_text(self):
        html = (
            '<a href="https://booth.pm/ja/items/10">商品A</a>'
            '<a href="/ja/items/11">商品B</a>'
            '<a href="https://booth.pm/ja/browse">一覧</a>'
        )
        self.assertEqual(
            utils._extract_urls_from_html(html),
            ["https://booth.pm/ja/items/10", "https://booth.pm/ja/items/11"],
        )

    def test_from_html_anchor_without_text_is_ignored(self):
        # 現状: handle_data でしか拾わないため、テキストの無い <a>（画像リンク等）は対象外
        html = '<a href="https://booth.pm/ja/items/10"><img src="x.png"></a>'
        self.assertEqual(utils._extract_urls_from_html(html), [])


class TestBoothMetaParser(unittest.TestCase):
    def test_reads_og_tags(self):
        p = utils.BoothMetaParser()
        p.feed(
            '<html><head>'
            '<meta property="og:title" content="商品タイトル - BOOTH">'
            '<meta property="og:image" content="https://example.invalid/i.png">'
            '<meta name="description" content="ignored">'
            '</head></html>'
        )
        self.assertEqual(p.og_title, "商品タイトル - BOOTH")
        self.assertEqual(p.og_image, "https://example.invalid/i.png")

    def test_missing_tags_stay_none(self):
        p = utils.BoothMetaParser()
        p.feed("<html><head><title>x</title></head></html>")
        self.assertIsNone(p.og_title)
        self.assertIsNone(p.og_image)


class TestScanFiles(unittest.TestCase):
    def test_two_level_scan_and_classification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ["a.zip", "b.UNITYPACKAGE", "readme.txt", "manual.pdf", "tex.psd", "s.PNG", "x.exe"]:
                (root / name).write_bytes(b"")
            sub = root / "sub"
            sub.mkdir()
            (sub / "c.zip").write_bytes(b"")
            (sub / "d.jpeg").write_bytes(b"")
            deep = sub / "deep"
            deep.mkdir()
            (deep / "e.zip").write_bytes(b"")  # 2階層目より下は対象外

            r = utils.scan_files_two_level(str(root))
            self.assertEqual(sorted(r["files"]["archives"]), ["a.zip", "b.UNITYPACKAGE", "c.zip"])
            self.assertEqual(sorted(r["files"]["documents"]), ["manual.pdf", "readme.txt"])
            self.assertEqual(r["files"]["sources"], ["tex.psd"])
            self.assertEqual(sorted(r["files"]["images"]), ["d.jpeg", "s.PNG"])
            self.assertEqual(
                r["stats"],
                {"archive_count": 3, "document_count": 2, "source_count": 1, "image_count": 2},
            )

    def test_missing_folder_returns_zero(self):
        r = utils.scan_files_two_level(os.path.join(tempfile.gettempdir(), "blh-does-not-exist-xyz"))
        self.assertEqual(sum(r["stats"].values()), 0)


class TestMetadataJson(unittest.TestCase):
    def test_missing_returns_empty_items(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(utils.read_metadata_json(td), {"items": []})

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            items = [{"title": "日本語", "path": "p"}]
            utils.write_metadata_json(td, items)
            self.assertEqual(utils.read_metadata_json(td), {"items": items})

    def test_broken_returns_empty_items(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "metadata.json").write_text("{oops", encoding="utf-8")
            self.assertEqual(utils.read_metadata_json(td), {"items": []})


if __name__ == "__main__":
    unittest.main()
