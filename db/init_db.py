"""
Скрипт инициализации БД. Запуск: python -m db.init_db
"""
import logging

from db.models import init_db

logging.basicConfig(level=logging.INFO)
init_db()
print("Готово. Таблица orders создана/проверена.")
