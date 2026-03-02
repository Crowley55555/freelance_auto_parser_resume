import logging
from logging.handlers import RotatingFileHandler
import os
import time
import asyncio
import pandas as pd

from dotenv import load_dotenv

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

# Получаем токен и ID чата из переменных окружения (в данном случае они уже не нужны)
TELEGRAM_TOKEN = os.getenv('TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Проверка загрузки переменных окружения
print(f'TOKEN: {TELEGRAM_TOKEN}')
print(f'TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}')

async def save_to_excel(data):
    """Функция для сохранения данных в Excel."""
    try:
        df = pd.DataFrame(data)  # Создаем DataFrame из данных
        df.to_excel('tasks.xlsx', index=False, engine='openpyxl')  # Записываем в Excel
        logger.info('Данные успешно сохранены в файл tasks.xlsx')
    except Exception as e:
        logger.error(f"Ошибка при сохранении в Excel: {e}")

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
    """Основная логика работы бота (с заменой на сохранение в Excel)."""
    # Проверяем доступность токенов (хотя они не используются в этом варианте)
    if not check_tokens():
        logger.critical("Один или оба токена недоступны. Программа завершена.")
        return

    old_data = []

    while True:
        try:
            # Получаем данные из парсера
            parsed_data = parser.parser()
            if not parsed_data:
                logger.warning("Нет данных для обработки.")
            
            # Логируем полученные данные
            logger.info(f"Полученные данные: {parsed_data}")

            # Сохраняем данные в Excel
            if parsed_data:
                await save_to_excel(parsed_data)
            
            old_data = parsed_data
            await asyncio.sleep(RETRY_TIME)

        except Exception as error:
            logger.exception(f"Ошибка в работе программы: {error}")
            await asyncio.sleep(RETRY_TIME)

if __name__ == '__main__':
    asyncio.run(main())
