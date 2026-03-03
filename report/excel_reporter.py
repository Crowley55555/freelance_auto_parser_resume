"""
Локальная отчётность в Excel (report.xlsx) с фиксированными колонками и retry при ошибке записи.
Колонки (строго по порядку): Биржа, Ссылка на заказ, Сопроводительное письмо, Дата отклика, Стоимость заказа.
"""
import asyncio
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

REPORT_PATH = Path(__file__).resolve().parent.parent / "report.xlsx"
COLUMNS = [
    "Биржа",
    "Ссылка на заказ",
    "Сопроводительное письмо",
    "Дата отклика",
    "Стоимость заказа",
]
RETRY_DELAY = 2
RETRY_COUNT = 3


def _ensure_file() -> None:
    """Создаёт файл с заголовками, если его нет."""
    if not REPORT_PATH.exists():
        df = pd.DataFrame(columns=COLUMNS)
        df.to_excel(REPORT_PATH, index=False, engine="openpyxl")
        logger.info("Создан файл отчёта: %s", REPORT_PATH)


def _append_row_sync(
    platform: str,
    url: str,
    cover_letter: str,
    date_response: str,
    budget: str,
) -> None:
    """Синхронная запись одной строки с retry (3 попытки, интервал 2 с)."""
    _ensure_file()
    row = {
        "Биржа": platform,
        "Ссылка на заказ": url,
        "Сопроводительное письмо": cover_letter or "",
        "Дата отклика": date_response,
        "Стоимость заказа": budget or "Не указан",
    }
    for attempt in range(RETRY_COUNT):
        try:
            df = pd.read_excel(REPORT_PATH, engine="openpyxl")
            # Привести колонки к нужному порядку (если в файле нет колонки «Биржа» — добавить)
            for c in COLUMNS:
                if c not in df.columns:
                    df[c] = ""
            df = df[COLUMNS]
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            df.to_excel(REPORT_PATH, index=False, engine="openpyxl")
            logger.info("Запись в отчёт добавлена: %s | %s", platform, url)
            return
        except Exception as e:
            logger.warning("Ошибка записи в Excel (попытка %s/%s): %s", attempt + 1, RETRY_COUNT, e)
            if attempt < RETRY_COUNT - 1:
                time.sleep(RETRY_DELAY)
            else:
                raise


async def append_row(
    platform: str,
    url: str,
    cover_letter: str,
    budget: Optional[str] = None,
) -> None:
    """
    Асинхронно добавляет строку в report.xlsx.
    platform: "fl.ru" или "Kwork".
    Дата отклика — момент вызова (нажатие кнопки подтверждения).
    """
    date_response = datetime.now().strftime("%Y-%m-%d %H:%M")
    await asyncio.to_thread(
        _append_row_sync,
        platform,
        url,
        cover_letter or "",
        date_response,
        budget if budget and budget.strip() else "Не указан",
    )
