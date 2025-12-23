import logging
from pathlib import Path

_LOGGER_INITIALIZED = False


def _init_logging():
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return

    log_dir = Path.home() / ".boothlibraryhelper"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "app.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    _LOGGER_INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    """
    アプリ共通の logger を取得する
    """
    _init_logging()
    return logging.getLogger(name)
