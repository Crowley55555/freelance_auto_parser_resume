"""
Состояние парсеров: время последней успешной проверки по платформам.
Используется для фильтра «изначально не старше 48ч» и «далее только новые заказы».
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "parser_state.json"
MAX_AGE_SECONDS = 48 * 3600  # 48 часов


def _ensure_data_dir() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_last_run_ts(platform: str) -> Optional[float]:
    """
    Возвращает Unix timestamp (UTC) последней проверки для платформы или None (первый запуск).
    """
    if not STATE_PATH.exists():
        return None
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get(platform)
        if not raw:
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.timestamp()
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug("Не удалось прочитать parser_state: %s", e)
        return None


def set_last_run(platform: str) -> None:
    """Сохраняет текущее время (UTC) как время последней проверки для платформы."""
    _ensure_data_dir()
    now = datetime.now(timezone.utc)
    data = {}
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError):
            pass
    data[platform] = now.isoformat()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def filter_by_time(
    orders: list,
    last_run_ts: Optional[float],
    *,
    strict_incremental: bool = True,
) -> list:
    """
    Фильтрует заказы по времени.
    - strict_incremental=False (RSS fl.ru): всегда окно 48ч — RSS обновляется с задержкой.
    - strict_incremental=True (Kwork): при наличии last_run — только новее last_run.
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - MAX_AGE_SECONDS
    if not strict_incremental or last_run_ts is None:
        return [o for o in orders if (o.get("published_ts") or 0) >= cutoff]
    return [o for o in orders if (o.get("published_ts") or 0) > last_run_ts]
