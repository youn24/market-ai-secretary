"""
共通ユーティリティ：ログ設定、ディレクトリ管理、JST時刻
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))

BASE_DIR = Path(__file__).parent.parent


def get_jst_now() -> datetime:
    return datetime.now(JST)


def get_today_str() -> str:
    return get_jst_now().strftime("%Y-%m-%d")


def get_dirs() -> dict:
    return {
        "data_raw":       BASE_DIR / "data" / "raw",
        "data_processed": BASE_DIR / "data" / "processed",
        "data_news":      BASE_DIR / "data" / "news",
        "reports":        BASE_DIR / "reports",
        "charts":         BASE_DIR / "reports" / "charts",
        "archive":        BASE_DIR / "reports" / "archive",
        "logs":           BASE_DIR / "logs",
    }


def ensure_dirs():
    for d in get_dirs().values():
        d.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str) -> logging.Logger:
    ensure_dirs()
    log_path = BASE_DIR / "logs" / f"{get_today_str()}.log"
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8-sig")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    import sys
    ch.stream = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, closefd=False)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def pct_change(current, previous) -> float | None:
    """前回比の変化率(%)を計算。どちらかがNoneなら None を返す。"""
    try:
        if previous and previous != 0:
            return round((current - previous) / abs(previous) * 100, 2)
    except Exception:
        pass
    return None


def sign_label(value) -> str:
    if value is None:
        return "N/A"
    if value > 0:
        return f"+{value:.2f}%"
    return f"{value:.2f}%"
