# app/utils.py
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Set

import requests
from html.parser import HTMLParser


ARCHIVE_EXTS = {".zip", ".unitypackage"}
DOCUMENT_EXTS = {".pdf", ".txt", ".md"}
SOURCE_EXTS = {".psd"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class BoothMetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.og_image: Optional[str] = None
        self.og_title: Optional[str] = None

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        attr = dict(attrs)
        prop = attr.get("property")
        if prop == "og:image":
            self.og_image = attr.get("content")
        elif prop == "og:title":
            self.og_title = attr.get("content")


def extract_product_id(folder_name: str) -> Optional[str]:
    """
    Folder name format: [123456] something
    """
    m = re.match(r"\[(\d+)\]", folder_name)
    return m.group(1) if m else None


def build_public_item_url(product_id: str) -> str:
    return f"https://booth.pm/ja/items/{product_id}"


def fetch_public_item_meta(
    product_id: str,
    session: Optional[requests.Session] = None,
    timeout_sec: int = 10,
) -> Optional[Dict[str, str]]:
    """
    Public booth.pm item page only.
    Returns: {"product_url": ..., "official_title": ..., "og_image_url": ...}
    """
    url = build_public_item_url(product_id)
    s = session or requests.Session()
    try:
        r = s.get(url, timeout=timeout_sec)
        r.raise_for_status()

        parser = BoothMetaParser()
        parser.feed(r.text)

        meta: Dict[str, str] = {"product_url": url}
        if parser.og_title:
            meta["official_title"] = parser.og_title
        if parser.og_image:
            meta["og_image_url"] = parser.og_image
        return meta
    except Exception:
        return None


def fetch_and_cache_thumbnail(
    item_path: str,
    session: Optional[requests.Session] = None,
    timeout_sec: int = 10,
    ttl_sec: int = 3600,
    force_refresh: bool = False,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Public booth.pm only.

    Cache per item folder:
      [item]/.thumbnail_cache/booth.<ext>
      [item]/.thumbnail_cache/meta.json

    Behavior:
      - If cached thumbnail exists AND meta.json exists AND within TTL => reuse (no extra requests)
      - If TTL expired (or force_refresh=True) => refetch public page meta, and re-download thumbnail only if needed
      - If refresh fails => falls back to existing cache when available

    Returns:
      (thumbnail_rel_path, meta_dict)
      thumbnail_rel_path example: ".thumbnail_cache/booth.jpg"
    """
    folder_name = os.path.basename(item_path)
    product_id = extract_product_id(folder_name)
    if not product_id:
        return None, None

    cache_dir = os.path.join(item_path, ".thumbnail_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Detect existing thumbnail file
    existing_rel: Optional[str] = None
    existing_path: Optional[str] = None
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(cache_dir, f"booth{ext}")
        if os.path.exists(p):
            existing_rel = f".thumbnail_cache/booth{ext}"
            existing_path = p
            break

    meta_path = os.path.join(cache_dir, "meta.json")
    existing_meta: Optional[Dict[str, Any]] = None
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                tmp = json.load(f)
            if isinstance(tmp, dict):
                existing_meta = tmp
        except Exception:
            existing_meta = None

    def _parse_utc_iso(s: Any) -> Optional[datetime]:
        if not isinstance(s, str) or not s.strip():
            return None
        ss = s.strip()
        try:
            # Accept both "2025-01-01T00:00:00" and "...Z"
            if ss.endswith("Z"):
                ss = ss[:-1]
            return datetime.fromisoformat(ss)
        except Exception:
            return None

    def _is_fresh(meta: Optional[Dict[str, Any]]) -> bool:
        if force_refresh:
            return False
        if ttl_sec is None or int(ttl_sec) <= 0:
            return False
        if not isinstance(meta, dict):
            return False
        dt = _parse_utc_iso(meta.get("fetched_at"))
        if not dt:
            return False
        age = (datetime.utcnow() - dt).total_seconds()
        return age < float(ttl_sec)

    # Fast path: cached & fresh
    if existing_rel and _is_fresh(existing_meta):
        return existing_rel, existing_meta

    # If we have a cached image but no meta, we can still return it (but try refresh below)
    s = session or requests.Session()
    meta = fetch_public_item_meta(product_id, session=s, timeout_sec=timeout_sec)
    if not meta:
        # refresh failed -> fallback to existing
        if existing_rel:
            return existing_rel, existing_meta
        return None, None

    og_image_url = meta.get("og_image_url")
    # If no image URL, still persist meta (title/url) and fallback to existing thumbnail when present
    if not og_image_url:
        try:
            meta_out = {
                "product_id": product_id,
                "product_url": meta.get("product_url", ""),
                "official_title": meta.get("official_title", ""),
                "og_image_url": "",
                "image_rel": existing_rel or "",
                "fetched_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_out, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return existing_rel, meta

    # If the og:image URL did not change and we already have an image, skip re-downloading
    if (
        (not force_refresh)
        and existing_rel
        and isinstance(existing_meta, dict)
        and str(existing_meta.get("og_image_url") or "").strip() == str(og_image_url).strip()
    ):
        try:
            meta_out = {
                "product_id": product_id,
                "product_url": meta.get("product_url", ""),
                "official_title": meta.get("official_title", ""),
                "og_image_url": og_image_url,
                "image_rel": existing_rel,
                "fetched_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_out, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return existing_rel, meta_out

    try:
        img = s.get(og_image_url, timeout=timeout_sec)
        img.raise_for_status()

        # Decide extension from URL or content-type
        ext: Optional[str] = None
        url_lower = str(og_image_url).lower()
        for cand in (".png", ".jpg", ".jpeg", ".webp"):
            if url_lower.endswith(cand):
                ext = cand
                break
        if not ext:
            ctype = (img.headers.get("Content-Type") or "").lower()
            if "png" in ctype:
                ext = ".png"
            elif "jpeg" in ctype or "jpg" in ctype:
                ext = ".jpg"
            elif "webp" in ctype:
                ext = ".webp"
            else:
                ext = ".jpg"

        # Normalize extension to a small set
        if ext == ".jpeg":
            ext = ".jpg"

        image_rel = f".thumbnail_cache/booth{ext}"
        image_path = os.path.join(cache_dir, f"booth{ext}")

        # If extension changed, remove old cached thumbnails
        if existing_path and os.path.abspath(existing_path) != os.path.abspath(image_path):
            try:
                os.remove(existing_path)
            except Exception:
                pass

        with open(image_path, "wb") as f:
            f.write(img.content)

        meta_out = {
            "product_id": product_id,
            "product_url": meta.get("product_url", ""),
            "official_title": meta.get("official_title", ""),
            "og_image_url": og_image_url,
            "image_rel": image_rel,
            "fetched_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_out, f, ensure_ascii=False, indent=2)

        return image_rel, meta_out
    except Exception:
        # download failed -> fallback to existing
        return existing_rel, meta


# ----------------------------
# File scanning (two-level)
# ----------------------------
def _scan_single_dir(dir_path: str, result: Dict[str, List[str]]) -> None:
    try:
        for e in os.scandir(dir_path):
            if not e.is_file():
                continue
            ext = os.path.splitext(e.name)[1].lower()
            if ext in ARCHIVE_EXTS:
                result["archives"].append(e.name)
            elif ext in DOCUMENT_EXTS:
                result["documents"].append(e.name)
            elif ext in SOURCE_EXTS:
                result["sources"].append(e.name)
            elif ext in IMAGE_EXTS:
                result["images"].append(e.name)
    except Exception:
        pass


def scan_files_two_level(folder_path: str) -> Dict[str, Any]:
    """
    Scan: folder_path (direct) + 1-level children directories
    """
    files = {"archives": [], "documents": [], "sources": [], "images": []}

    _scan_single_dir(folder_path, files)

    try:
        for e in os.scandir(folder_path):
            if e.is_dir():
                _scan_single_dir(e.path, files)
    except Exception:
        pass

    stats = {
        "archive_count": len(files["archives"]),
        "document_count": len(files["documents"]),
        "source_count": len(files["sources"]),
        "image_count": len(files["images"]),
    }

    return {"files": files, "stats": stats}


def read_metadata_json(root_folder: str) -> Dict[str, Any]:
    path = os.path.join(root_folder, "metadata.json")
    if not os.path.exists(path):
        return {"items": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"items": []}


def write_metadata_json(root_folder: str, items: List[Dict[str, Any]]) -> None:
    path = os.path.join(root_folder, "metadata.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)


# ----------------------------
# purchase_import.json generation / apply
# ----------------------------
class PurchaseHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: List[str] = []
        self._in_a = False
        self._href = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attr = dict(attrs)
            href = attr.get("href", "")
            if href:
                self._in_a = True
                self._href = href

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_a = False
            self._href = ""

    def handle_data(self, data):
        if not self._in_a:
            return
        if not self._href:
            return
        href = self._href.strip()
        if "/items/" in href:
            self.urls.append(href)


def _normalize_item_url(url: str) -> Optional[str]:
    if not isinstance(url, str):
        return None
    u = url.strip()
    if not u:
        return None

    if u.startswith("//"):
        u = "https:" + u

    if u.startswith("/"):
        u = "https://booth.pm" + u

    if not u.startswith("http://") and not u.startswith("https://"):
        return None

    m = re.search(r"/items/(\d+)", u)
    if not m:
        return None
    pid = m.group(1)
    return build_public_item_url(pid)


def _extract_urls_from_text(pasted_text: str) -> List[str]:
    urls = []
    for line in pasted_text.splitlines():
        line = line.strip()
        if not line:
            continue
        u = _normalize_item_url(line)
        if u:
            urls.append(u)
    return urls


def _extract_urls_from_html(html_text: str) -> List[str]:
    parser = PurchaseHTMLParser()
    parser.feed(html_text)
    normalized = []
    for u in parser.urls:
        nu = _normalize_item_url(u)
        if nu:
            normalized.append(nu)
    return normalized


def _load_existing_items_map(root_folder: str) -> Dict[str, Dict[str, Any]]:
    meta = read_metadata_json(root_folder)
    out: Dict[str, Dict[str, Any]] = {}
    if not meta or not isinstance(meta.get("items"), list):
        return out
    for it in meta["items"]:
        pid = str(it.get("product_id", "")).strip()
        if pid.lower() == "none":
            pid = ""
        if not pid:
            continue
        out[pid] = it
    return out


def _filter_urls_by_existing_folders(urls: List[str], root_folder: str) -> Tuple[List[str], int]:
    """
    Remove URLs whose product_id doesn't exist in local DL folders.
    """
    existing = _load_existing_items_map(root_folder)
    filtered = []
    removed = 0
    for u in urls:
        m = re.search(r"/items/(\d+)", u)
        if not m:
            removed += 1
            continue
        pid = m.group(1)
        if pid not in existing:
            removed += 1
            continue
        filtered.append(u)
    return filtered, removed


def _write_purchase_json(
    out_path: str,
    items: List[Dict[str, Any]],
    source_type: str,
    source_hint: str,
    extra_source: Optional[Dict[str, Any]] = None,
) -> None:
    data = {
        "source": {
            "type": source_type,
            "hint": source_hint,
            "generated_at": datetime.utcnow().isoformat(),
        },
        "items": items,
    }
    if extra_source:
        data["source"].update(extra_source)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_purchase_json_from_urls_and_html(
    pasted_text: str,
    out_path: str,
    source_hint: str = "",
    filter_root_folder: Optional[str] = None,
) -> Dict[str, Any]:
    urls = _extract_urls_from_text(pasted_text)
    html_urls = _extract_urls_from_html(pasted_text)
    urls.extend(html_urls)

    uniq: List[str] = []
    seen: Set[str] = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)

    extracted = len(uniq)
    extra_source: Dict[str, Any] = {}

    if filter_root_folder:
        uniq, removed = _filter_urls_by_existing_folders(uniq, filter_root_folder)
        extra_source["filtered_out"] = removed

    items = []
    for u in uniq:
        m = re.search(r"/items/(\d+)", u)
        if not m:
            continue
        pid = m.group(1)
        items.append({"product_id": pid, "product_url": u})

    _write_purchase_json(
        out_path=out_path,
        items=items,
        source_type="manual_paste",
        source_hint=source_hint,
        extra_source=extra_source,
    )
    return {"extracted": extracted, "filtered_out": int(extra_source.get("filtered_out", 0) or 0), "out_path": out_path}


def build_purchase_json_from_html_files(
    html_file_paths: List[str],
    out_path: str,
    source_hint: str = "",
    filter_root_folder: Optional[str] = None,
) -> Dict[str, Any]:
    urls: List[str] = []
    files_used: List[str] = []
    for p in html_file_paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                html = f.read()
            files_used.append(os.path.basename(p))
            urls.extend(_extract_urls_from_html(html))
        except Exception:
            continue

    uniq: List[str] = []
    seen: Set[str] = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)

    extracted = len(uniq)
    extra_source: Dict[str, Any] = {}

    if filter_root_folder:
        uniq, removed = _filter_urls_by_existing_folders(uniq, filter_root_folder)
        extra_source["filtered_out"] = removed

    items = []
    for u in uniq:
        m = re.search(r"/items/(\d+)", u)
        if not m:
            continue
        pid = m.group(1)
        items.append({"product_id": pid, "product_url": u})

    _write_purchase_json(
        out_path=out_path,
        items=items,
        source_type="manual_copy_html",
        source_hint=source_hint or (files_used[0] + f" (+{len(files_used)-1} files)" if files_used else ""),
        extra_source=extra_source,
    )
    stats: Dict[str, Any] = {}
    stats.update(
        {
            "extracted": extracted,
            "filtered_out": int(extra_source.get("filtered_out", 0) or 0),
            "out_path": out_path,
        }
    )
    return stats


def apply_purchase_import_json(root_folder: str, purchase_json_path: str) -> Dict[str, Any]:
    meta = read_metadata_json(root_folder)
    if not meta or not isinstance(meta.get("items"), list):
        return {"total": 0, "matched": 0, "updated": 0}

    try:
        with open(purchase_json_path, "r", encoding="utf-8") as f:
            purchase = json.load(f)
    except Exception:
        return {"total": 0, "matched": 0, "updated": 0}

    items = purchase.get("items", [])
    if not isinstance(items, list):
        return {"total": 0, "matched": 0, "updated": 0}

    src_map: Dict[str, Dict[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("product_id", "")).strip()
        if not pid:
            continue
        src_map[pid] = it

    total = len(src_map)
    matched = 0
    updated = 0

    for it in meta.get("items", []):
        pid = str(it.get("product_id", "")).strip()
        if pid.lower() == "none":
            pid = ""
        if not pid:
            pid = extract_product_id(str(it.get("title", "")) or "") or ""

        if not pid:
            continue

        src = src_map.get(pid)
        if not src:
            continue

        matched += 1
        changed = False

        pu = src.get("product_url")
        if isinstance(pu, str) and pu.strip():
            if it.get("product_url") != pu.strip():
                it["product_url"] = pu.strip()
                changed = True

        # optional fields
        pt = src.get("purchase_title") or src.get("official_title")
        if isinstance(pt, str) and pt.strip():
            if it.get("purchase_title") != pt.strip():
                it["purchase_title"] = pt.strip()
                changed = True

        pa = src.get("purchased_at")
        if isinstance(pa, str) and pa.strip():
            if it.get("purchased_at") != pa.strip():
                it["purchased_at"] = pa.strip()
                changed = True

        if changed:
            updated += 1

    write_metadata_json(root_folder, meta.get("items", []))
    return {"total": total, "matched": matched, "updated": updated}
