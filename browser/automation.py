"""
Автоматизация fl.ru через Playwright (Firefox): постоянный контекст, только заполнение формы.
Бот не нажимает «Отправить» и не ждёт ответа сервера. Вкладка остаётся открытой.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import async_playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeout

from config.loader import load_selectors
from ai.llm_service import generate_cover_letter

load_dotenv()
logger = logging.getLogger(__name__)

RESUME_PATH = os.getenv("RESUME_PATH", "./assets/resume.pdf")
USER_DATA_DIR = Path(__file__).resolve().parent.parent / "browser_profile"


def _get_resume_path() -> Optional[Path]:
    """Проверяет наличие файла резюме. Возвращает Path или None."""
    p = Path(RESUME_PATH)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / p
    return p if p.exists() else None


def _first_selector(selectors_str: str) -> list[str]:
    """Разбивает строку селекторов (через запятую) и возвращает список без пустых."""
    return [s.strip() for s in selectors_str.split(",") if s.strip()]


async def _get_description_from_page(page: Page, selectors: dict) -> str:
    """Извлекает текст описания задачи со страницы заказа."""
    desc_selectors = _first_selector(selectors.get("order", {}).get("description", ".b-post__txt"))
    for sel in desc_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=5000)
            if el:
                return (await el.inner_text()).strip() or ""
        except PlaywrightTimeout:
            continue
    logger.warning("Не удалось найти описание задачи ни одним селектором")
    return ""


async def _fill_form(
    page: Page,
    selectors: dict,
    cover_letter: str,
    resume_path: Optional[Path],
) -> None:
    """
    Заполняет поле отклика и прикрепляет резюме (если есть).
    Кнопку «Отправить» не нажимает — пользователь отправляет вручную.
    """
    order_sel = selectors.get("order", {})
    input_selectors = _first_selector(order_sel.get("cover_letter_input", "textarea[name='descr']"))
    for sel in input_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=5000)
            if el:
                await el.fill(cover_letter)
                break
        except PlaywrightTimeout:
            continue
    else:
        raise RuntimeError("Не найдено поле для текста отклика")

    if resume_path:
        file_selectors = _first_selector(order_sel.get("resume_file_input", "input[type='file']"))
        for sel in file_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.set_input_files(str(resume_path))
                    break
            except Exception as e:
                logger.debug("Не удалось прикрепить файл по селектору %s: %s", sel, e)
        else:
            logger.warning("Не найдено поле для прикрепления файла, отклик только текстом")


# Глобальный контекст браузера (запускается при первом использовании)
_playwright = None
_context: Optional[BrowserContext] = None


async def get_browser_context() -> BrowserContext:
    """Возвращает постоянный контекст браузера Firefox (user_data_dir). Вкладка не закрывается скриптом."""
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
    Открывает заказ в новой вкладке Firefox, парсит описание, генерирует отклик через ИИ,
    вставляет текст в форму и прикрепляет резюме. Останавливается — пользователь сам
    нажимает «Отправить» на сайте. Вкладку скрипт не закрывает.
    Возвращает сгенерированный текст отклика (cover_letter).
    """
    resume_path = _get_resume_path()
    if not resume_path:
        logger.warning(
            "Файл резюме не найден по пути RESUME_PATH=%s. Бот запущен в режиме только текста.",
            RESUME_PATH,
        )

    selectors = load_selectors()
    context = await get_browser_context()
    page = await context.new_page()
    cover_letter = ""

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1)

        description = await _get_description_from_page(page, selectors)
        if not description:
            description = "Описание задачи не удалось извлечь. Напишите краткий отклик как Python-разработчик."

        cover_letter = await generate_cover_letter(description)
        await _fill_form(page, selectors, cover_letter, resume_path)
        # Не нажимаем кнопку отправки и не ждём ответа — вкладка остаётся открытой
        return cover_letter
    except Exception as e:
        logger.exception("Ошибка при подготовке отклика: %s", e)
        raise
