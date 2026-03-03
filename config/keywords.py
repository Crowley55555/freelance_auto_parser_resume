"""
Умный фильтр ключевых слов для отбора релевантных заказов (регистронезависимый поиск).
Перед отправкой уведомления в Telegram вызывается is_relevant_order(text).
"""
from typing import List

# Список слов/фраз для фильтрации (хотя бы одно совпадение — заказ релевантен)
KEYWORDS: List[str] = [
    # Основные
    "Python",
    "Пайтон",
    "Backend",
    "Бэкенд",
    "Server-side",
    "API Development",
    "Разработка API",
    "Web Development",
    "Веб-разработка",
    "Scripting",
    "Скрипты",
    "Automation",
    "Автоматизация",
    # Фреймворки
    "Django",
    "Джанго",
    "Flask",
    "Фласк",
    "FastAPI",
    "Tornado",
    "Pyramid",
    "DRF",
    "Django REST Framework",
    # API/БД
    "REST API",
    "GraphQL",
    "SQLAlchemy",
    "PostgreSQL",
    "MySQL",
    "SQLite",
    "Redis",
    "Celery",
    # Боты
    "Telegram Bot",
    "Телеграм бот",
    "Discord Bot",
    "Дискорд бот",
    "WhatsApp Bot",
    "Aiogram",
    "Telebot",
    "PyTelegramBotAPI",
    "Chatbot",
    "Чат-бот",
    "Bot Integration",
    # Парсинг
    "Web Scraping",
    "Парсинг сайтов",
    "Data Scraping",
    "Selenium",
    "Scrapy",
    "BeautifulSoup",
    "BS4",
    "Parsing",
    "Парсер",
    "Data Extraction",
    "Извлечение данных",
    # Офис/Интеграции
    "Excel Automation",
    "Автоматизация Excel",
    "Google Sheets API",
    "Refactoring",
    "Рефакторинг",
    "Optimization",
    "Оптимизация",
    "Integration",
    "Интеграция",
    # Прочее
    "MVP",
    # Комбинации
    "Python Django REST",
    "Python Telegram Bot Payment",
    "Python Script Automation",
    "Fix Python Error",
    "Scrape Website to CSV",
    "Deploy Python App",
]


def is_relevant_order(text: str) -> bool:
    """
    Проверяет, релевантен ли заказ по ключевым словам (регистронезависимый поиск).
    text — объединённые заголовок и описание заказа (или только заголовок).
    Возвращает True, если найдено хотя бы одно совпадение.
    """
    if not text or not text.strip():
        return False
    lower = text.lower()
    for keyword in KEYWORDS:
        if keyword.lower() in lower:
            return True
    return False
