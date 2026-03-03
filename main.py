"""
Точка входа: инициализация БД, проверка конфигурации, запуск бота и фонового парсера.
"""
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from db.models import init_db
from bot.handlers import router, run_parser_and_notify
from bot.menu_handlers import router as menu_router
from browser.automation import close_browser

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s, %(levelname)s, %(message)s",
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RESUME_PATH = os.getenv("RESUME_PATH", "./assets/resume.pdf")
PARSER_INTERVAL_SEC = 60


def check_resume_path() -> None:
    """Проверяет наличие файла резюме и пишет предупреждение в лог при отсутствии."""
    p = Path(RESUME_PATH)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    if not p.exists():
        logger.warning(
            "Файл резюме не найден по пути RESUME_PATH=%s. Отклики будут только текстом.",
            RESUME_PATH,
        )
    else:
        logger.info("Файл резюме найден: %s", p)


async def parser_loop(bot: Bot, chat_id: str) -> None:
    """Периодически парсит RSS и отправляет новые заказы в Telegram."""
    while True:
        try:
            await run_parser_and_notify(bot, int(chat_id))
        except Exception as e:
            logger.exception("Ошибка в цикле парсера: %s", e)
        await asyncio.sleep(PARSER_INTERVAL_SEC)


async def main() -> None:
    if not TELEGRAM_TOKEN:
        logger.critical("Не задан TOKEN или TELEGRAM_TOKEN в .env")
        return
    if not TELEGRAM_CHAT_ID:
        logger.critical("Не задан TELEGRAM_CHAT_ID в .env")
        return

    init_db()
    check_resume_path()

    bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(menu_router)
    dp.include_router(router)

    # Фоновый парсер
    asyncio.create_task(parser_loop(bot, TELEGRAM_CHAT_ID))
    logger.info("Парсер запущен: проверка новых заказов каждые %s с.", PARSER_INTERVAL_SEC)

    try:
        await dp.start_polling(bot)
    finally:
        await close_browser()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
