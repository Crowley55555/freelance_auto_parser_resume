"""
Общая логика автоматизации браузера (DRY): работа с селекторами, заполнение формы, резюме.
Используется и fl.ru, и Kwork — без дублирования кода (Single Responsibility).
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

# Тексты кнопок «Откликнуться» / «Предложить услугу» для поиска по контенту
APPLY_BUTTON_TEXTS = ("Откликнуться", "Предложить услугу", "Предложить", "Написать сообщение")

# Базовый путь к проекту для относительного RESUME_PATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_resume_path(resume_path_env: Optional[str] = None) -> Optional[Path]:
    """
    Возвращает Path к файлу резюме из переменной окружения или None, если файл не найден.
    Одна реализация для всех платформ.
    """
    raw = resume_path_env or os.getenv("RESUME_PATH", "./assets/resume.pdf")
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p if p.exists() else None


def first_selector(selectors_str: str) -> list[str]:
    """Разбивает строку селекторов (через запятую) и возвращает список без пустых."""
    return [s.strip() for s in selectors_str.split(",") if s.strip()]


async def click_apply_button_if_present(
    page: Page,
    selectors: dict,
    timeout_ms: int = 5000,
) -> bool:
    """
    Нажимает кнопку «Откликнуться» / «Предложить услугу», если она есть (раскрывает форму).
    Возвращает True, если клик выполнен, иначе False. Не бросает исключений.
    """
    order_sel = selectors.get("order", {})
    apply_selectors = first_selector(order_sel.get("apply_button", ""))
    for sel in apply_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout_ms, state="visible")
            if el:
                box = await el.bounding_box()
                if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                    await el.click()
                    logger.info("Нажата кнопка «Откликнуться» по селектору: %s", sel)
                    await asyncio.sleep(1.5)
                    return True
        except PlaywrightTimeout:
            continue
        except Exception as e:
            logger.debug("Клик по селектору %s: %s", sel, e)
            continue

    for text in APPLY_BUTTON_TEXTS:
        try:
            loc = page.get_by_text(text, exact=False)
            if await loc.count() > 0:
                first_btn = loc.first
                if await first_btn.is_visible():
                    await first_btn.click()
                    logger.info("Нажата кнопка «%s» (по тексту)", text)
                    await asyncio.sleep(1.5)
                    return True
        except PlaywrightTimeout:
            continue
        except Exception as e:
            logger.debug("Клик по тексту «%s»: %s", text, e)
            continue

    return False


async def get_description_from_page(
    page: Page,
    selectors: dict,
    default_selector: str = ".b-post__txt",
    warn_message: str = "Не удалось найти описание задачи",
) -> str:
    """
    Извлекает текст описания задачи со страницы по первому сработавшему селектору.
    """
    desc_selectors = first_selector(selectors.get("order", {}).get("description", default_selector))
    for sel in desc_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=5000)
            if el:
                return (await el.inner_text()).strip() or ""
        except PlaywrightTimeout:
            continue
    logger.warning("%s", warn_message)
    return ""


async def fill_form(
    page: Page,
    selectors: dict,
    cover_letter: str,
    resume_path: Optional[Path],
    default_input: str = "textarea[name='descr']",
    default_file: str = "input[type='file']",
    error_input_message: str = "Не найдено поле для текста отклика",
) -> None:
    """
    Заполняет поле отклика и прикрепляет резюме (если путь передан).
    Кнопку «Отправить» не нажимает — пользователь отправляет вручную (единая политика для всех платформ).
    """
    order_sel = selectors.get("order", {})
    input_selectors = first_selector(order_sel.get("cover_letter_input", default_input))
    for sel in input_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=5000)
            if el:
                await el.fill(cover_letter)
                break
        except PlaywrightTimeout:
            continue
    else:
        raise RuntimeError(error_input_message)

    if resume_path:
        file_selectors = first_selector(order_sel.get("resume_file_input", default_file))
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
