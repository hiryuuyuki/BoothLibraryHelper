import os
import json
from pathlib import Path
from datetime import datetime

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        # UTF-8 with BOM friendly
        with open(SETTINGS_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(settings: dict):
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_last_dl_folder() -> str | None:
    settings = load_settings()
    p = settings.get("last_dl_folder")
    if not isinstance(p, str) or not p.strip():
        return None
    p = os.path.normpath(p.strip())
    return p if os.path.exists(p) else None


def set_last_dl_folder(path: str):
    # Normalize absolute path
    try:
        p = os.path.normpath(str(Path(path).resolve()))
    except Exception:
        p = os.path.normpath(path)

    # Guard: do not store non-existing path
    try:
        if not os.path.exists(p):
            return
    except Exception:
        return

    settings = load_settings()
    settings["last_dl_folder"] = p
    settings["last_dl_folder_updated_at"] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    save_settings(settings)


def get_ui_state() -> dict:
    settings = load_settings()
    st = settings.get("ui_state")
    return st if isinstance(st, dict) else {}


def set_ui_state(state: dict):
    if not isinstance(state, dict):
        return
    settings = load_settings()
    settings["ui_state"] = state
    settings["ui_state_updated_at"] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    save_settings(settings)
