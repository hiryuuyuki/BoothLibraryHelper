# app/storage.py
import os
from typing import Dict, Any, List
from app.settings import get_last_dl_folder

from app.logger import get_logger
from app.utils import (
    extract_product_id,
    build_public_item_url,
    fetch_public_item_meta,
    fetch_and_cache_thumbnail,
    scan_files_two_level,
    write_metadata_json,
    read_metadata_json,
)

logger = get_logger(__name__)


def scan_dl_folder(root_folder: str, max_depth: int = 2, diff: bool = True, public_ttl_sec: int = 3600, public_force_refresh: bool = False) -> Dict[str, Any]:
    """
    Root folder contains item folders like: [123456] Product Name

    Safety:
      - NEVER accesses accounts.booth.pm
      - Only accesses public booth.pm item pages (optional) for og:image / og:title
      - Public thumbnail/title are refreshed with TTL (default: 1 hour) to reflect latest updates
        (set public_force_refresh=True to force refresh).
    """
    prev = read_metadata_json(root_folder) if diff else None
    prev_map: Dict[str, Dict[str, Any]] = {}
    if prev and isinstance(prev.get("items"), list):
        for it in prev["items"]:
            p = it.get("path")
            if isinstance(p, str) and p:
                prev_map[p] = it

    session = None  # lazy create only if needed
    items: List[Dict[str, Any]] = []
    total_archives = 0
    total_documents = 0

    for name in os.listdir(root_folder):
        item_path = os.path.join(root_folder, name)
        if not os.path.isdir(item_path):
            continue

        item: Dict[str, Any] = {
            "title": name,
            "path": item_path,
            "product_id": "",
            "product_url": "",
            "official_title": "",
            "purchase_title": "",
            "purchased_at": "",
            "files": {
                "archives": [],
                "documents": [],
                "sources": [],
            },
            "stats": {
                "archive_count": 0,
                "document_count": 0,
                "source_count": 0,
                "image_count": 0,
            },
            "thumbnail": "",  # display-only
        }

        prev_item = prev_map.get(item_path)
        if prev_item and isinstance(prev_item, dict):
            pt = prev_item.get("purchase_title")
            pa = prev_item.get("purchased_at")
            item["purchase_title"] = pt.strip() if isinstance(pt, str) else ""
            item["purchased_at"] = pa.strip() if isinstance(pa, str) else ""

        scanned = scan_files_two_level(item_path)
        item["files"] = scanned.get("files", item["files"])
        item["stats"] = scanned.get("stats", item["stats"])

        pid = extract_product_id(name)
        if pid:
            item["product_id"] = pid
            item["product_url"] = build_public_item_url(pid)

        try:
            if pid:
                if session is None:
                    import requests

                    session = requests.Session()

                thumb_rel, meta = fetch_and_cache_thumbnail(item_path, session=session, timeout_sec=10, ttl_sec=public_ttl_sec, force_refresh=public_force_refresh)
                if thumb_rel:
                    item["thumbnail"] = thumb_rel

                if isinstance(meta, dict):
                    ot = meta.get("official_title")
                    if isinstance(ot, str) and ot.strip():
                        item["official_title"] = ot.strip()
                    pu = meta.get("product_url")
                    if isinstance(pu, str) and pu.strip():
                        item["product_url"] = pu.strip()
                else:
                    meta2 = fetch_public_item_meta(pid, session=session, timeout_sec=10)
                    if isinstance(meta2, dict):
                        ot = meta2.get("official_title")
                        if isinstance(ot, str) and ot.strip():
                            item["official_title"] = ot.strip()
                        pu = meta2.get("product_url")
                        if isinstance(pu, str) and pu.strip():
                            item["product_url"] = pu.strip()
        except Exception:
            logger.exception("thumbnail/meta fetch failed (public page)")

        if not item["thumbnail"] and prev_item and isinstance(prev_item, dict):
            t = prev_item.get("thumbnail")
            if isinstance(t, str) and t.strip():
                item["thumbnail"] = t.strip()

        total_archives += int(item["stats"].get("archive_count", 0) or 0)
        total_documents += int(item["stats"].get("document_count", 0) or 0)

        items.append(item)

    write_metadata_json(root_folder, items)

    return {
        "count": len(items),
        "archives": total_archives,
        "documents": total_documents,
    }


def scan_last_dl_folder(
    max_depth: int = 2,
    diff: bool = True,
    public_ttl_sec: int = 3600,
    public_force_refresh: bool = False,
) -> Dict[str, Any]:
    """Scan using last remembered DL folder. Returns same dict as scan_dl_folder."""
    root = get_last_dl_folder()
    if not root:
        raise FileNotFoundError("last_dl_folder is not set or does not exist")
    return scan_dl_folder(
        root,
        max_depth=max_depth,
        diff=diff,
        public_ttl_sec=public_ttl_sec,
        public_force_refresh=public_force_refresh,
    )
