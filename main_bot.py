import logging
from logging.handlers import RotatingFileHandler
import os
import time
import asyncio

from dotenv import load_dotenv
import telegram

import parser

RETRY_TIME = 60

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s, %(levelname)s, %(message)s',
    handlers=[
        RotatingFileHandler(
            filename='fl_new_work_bot.log',
            maxBytes=50000000,
            backupCount=5),
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получаем токен и ID чата из переменных окружения
TELEGRAM_TOKEN = os.getenv('TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Проверка загрузки переменных окружения
print(f'TOKEN: {TELEGRAM_TOKEN}')
print(f'TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}')

async def send_message(bot, message):
    """Функция для отправки сообщения ботом."""
    try:
        await bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(f'Сообщение отправлено: {message}')
    except telegram.TelegramError as e:
        logger.exception(f'Ошибка при отправке сообщения: {e}')

def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = [
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID
    ]
    for token in tokens:
        if token is None:
            logger.critical(f'Отсутствует токен {token}')
            return False
    return True

async def main():
    """Основная логика работы бота."""
    # Проверяем доступность токенов
    if not check_tokens():
        logger.critical("Один или оба токена недоступны. Программа завершена.")
        return

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    old_data = []

    while True:
        try:
            # Получаем данные из парсера
            parsed_data = parser.parser()
            if not parsed_data:
                logger.warning("Нет данных для отправки.")
            
            # Логируем полученные данные
            logger.info(f"Полученные данные: {parsed_data}")

            for data in parsed_data:
                # Фильтруем задачи, оставляем только те, в которых есть слово "Скрипт"
                if "Скрипт" in data['Задача']:
                    message = data['Задача'] + '\n' + data['Ссылка']
                    await send_message(bot, message)
                    time.sleep(5)
            
            old_data = parsed_data
            await asyncio.sleep(RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            await send_message(bot, message)
            logger.exception(f"Ошибка в работе программы: {error}")
            await asyncio.sleep(RETRY_TIME)

if __name__ == '__main__':
    asyncio.run(main())
