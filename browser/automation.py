"""
Автоматизация fl.ru через Playwright (Firefox): постоянный контекст, только заполнение формы.
Использует общую логику из browser.base (DRY). Бот не нажимает «Отправить».
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import async_playwright, BrowserContext

from config.loader import load_selectors
from ai.llm_service import generate_cover_letter
from browser.base import (
    get_resume_path,
    get_description_from_page,
    fill_form,
)
from browser.base import PROJECT_ROOT

load_dotenv()
logger = logging.getLogger(__name__)

USER_DATA_DIR = PROJECT_ROOT / "browser_profile"

# Глобальный контекст браузера (один на всё приложение — единственная точка входа для Firefox)
_playwright = None
_context: Optional[BrowserContext] = None


async def get_browser_context() -> BrowserContext:
    """Возвращает постоянный контекст браузера Firefox (user_data_dir)."""
    global _playwright, _context
    if _context is not None:
        return _context
    _playwright = await async_playwright().start()
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _context = await _playwright.firefox.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=False,
        locale="ru-RU",
    )
    logger.info("Браузер Firefox запущен, профиль: %s", USER_DATA_DIR)
    return _context


async def close_browser() -> None:
    """Закрывает браузер и Playwright."""
    global _context, _playwright
    if _context:
        await _context.close()
        _context = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


async def process_order(url: str, order_id: int) -> str:
    """
    Открывает заказ fl.ru в новой вкладке Firefox: парсит описание, генерирует отклик через ИИ,
    заполняет форму и прикрепляет резюме. Не нажимает «Отправить». Возвращает текст отклика.
    """
    resume_path = get_resume_path()
    if not resume_path:
        logger.warning(
            "Файл резюме не найден по пути RESUME_PATH. Бот запущен в режиме только текста."
        )

    selectors = load_selectors()
    context = await get_browser_context()
    page = await context.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1)

        description = await get_description_from_page(
            page,
            selectors,
            default_selector=".b-post__txt",
            warn_message="Не удалось найти описание задачи ни одним селектором",
        )
        if not description:
            description = "Описание задачи не удалось извлечь. Напишите краткий отклик как Python-разработчик."

        cover_letter = await generate_cover_letter(description)
        await fill_form(
            page,
            selectors,
            cover_letter,
            resume_path,
            default_input="textarea[name='descr']",
            error_input_message="Не найдено поле для текста отклика",
        )
        return cover_letter
    except Exception as e:
        logger.exception("Ошибка при подготовке отклика: %s", e)
        raise
