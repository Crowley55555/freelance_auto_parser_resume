"""
Автоматизация Kwork через тот же Firefox persistent_context.
Использует общую логику из browser.base (DRY). Кнопку отправки не нажимаем.
"""
import asyncio
import logging

from dotenv import load_dotenv

from config.loader import load_selectors_kwork
from ai.llm_service import generate_cover_letter
from browser.automation import get_browser_context, invalidate_browser_context
from browser.base import (
    get_resume_path,
    get_description_from_page,
    fill_form,
    click_apply_button_if_present,
)

load_dotenv()
logger = logging.getLogger(__name__)


async def process_order_kwork(url: str, order_id: int) -> str:
    """
    Открывает заказ Kwork в новой вкладке Firefox: парсит ТЗ, генерирует отклик,
    заполняет форму и прикрепляет резюме. Не нажимает «Отправить». Возвращает текст отклика.
    """
    resume_path = get_resume_path()
    if not resume_path:
        logger.warning("Файл резюме не найден: RESUME_PATH.")

    selectors = load_selectors_kwork()
    for attempt in (1, 2):
        try:
            context = await get_browser_context()
            page = await context.new_page()
            break
        except Exception as e:
            if "closed" in str(e).lower() and attempt == 1:
                logger.warning("Kwork: браузер был закрыт, перезапускаю окно: %s", e)
                invalidate_browser_context()
                continue
            raise

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1)

        await click_apply_button_if_present(page, selectors)

        description = await get_description_from_page(
            page,
            selectors,
            default_selector=".wysiwyg",
            warn_message="Kwork: не удалось найти описание задачи",
        )
        if not description:
            description = "Описание задачи не удалось извлечь. Напишите краткий отклик как Python-разработчик."

        cover_letter = await generate_cover_letter(description)
        await fill_form(
            page,
            selectors,
            cover_letter,
            resume_path,
            default_input="textarea[name='message']",
            error_input_message="Kwork: не найдено поле для текста отклика",
        )
        return cover_letter
    except Exception as e:
        logger.exception("Kwork: ошибка при подготовке отклика: %s", e)
        raise
