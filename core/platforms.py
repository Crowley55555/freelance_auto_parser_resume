"""
Единый источник правды для платформ (fl.ru, Kwork): константы, префиксы, отображаемые имена.
Соответствует DRY и Single Responsibility — одно место для маркировки бирж.
"""
from typing import Callable

# Импортируем константы БД, чтобы не дублировать строки
from db.models import PLATFORM_FL_RU, PLATFORM_KWORK

# Префиксы для сообщений и карточек в боте
PREFIX_FL = "🟦 fl.ru |"
PREFIX_KWORK = "🟣 Kwork |"

# Отображаемые имена для Excel и уведомлений
DISPLAY_NAME_FL = "fl.ru"
DISPLAY_NAME_KWORK = "Kwork"


def get_prefix(platform: str) -> str:
    """Возвращает префикс для сообщения (🟦 fl.ru | или 🟣 Kwork |)."""
    return PREFIX_KWORK if platform == PLATFORM_KWORK else PREFIX_FL


def get_display_name(platform: str) -> str:
    """Возвращает отображаемое имя биржи (fl.ru или Kwork)."""
    return DISPLAY_NAME_KWORK if platform == PLATFORM_KWORK else DISPLAY_NAME_FL


def normalize_platform(platform: str | None) -> str:
    """Возвращает платформу по умолчанию (fl_ru), если передано None или пусто."""
    return platform if platform in (PLATFORM_FL_RU, PLATFORM_KWORK) else PLATFORM_FL_RU
