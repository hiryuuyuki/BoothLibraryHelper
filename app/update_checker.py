"""
update_checker.py
将来のアップデート通知専用（自動更新は行わない）
"""

import requests
from app.version import VERSION

UPDATE_INFO_URL = "https://example.com/boothlibraryhelper/version.json"

def check_update():
    """
    アップデートがあるかどうかだけを確認する
    実際のダウンロード・実行は行わない
    """
    try:
        res = requests.get(UPDATE_INFO_URL, timeout=5)
        res.raise_for_status()
        data = res.json()

        latest = data.get("latest_version")
        if latest and latest != VERSION:
            return {
                "has_update": True,
                "latest": latest,
                "url": data.get("release_page")
            }
    except Exception:
        pass

    return {"has_update": False}
