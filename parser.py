import re
import calendar
import feedparser
import logging

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s, %(levelname)s, %(message)s')
logger = logging.getLogger(__name__)

RSS_URL = "https://www.fl.ru/rss/?category=5"


def _fl_order_id_from_url(url: str) -> str:
    """Извлекает идентификатор заказа из URL fl.ru (или возвращает сам URL как id)."""
    if not url:
        return ""
    # Пример: https://www.fl.ru/projects/123456/...
    m = re.search(r"/projects?/(\d+)", url)
    return m.group(1) if m else url


def parser():
    """
    Парсит RSS-ленту с задачами с сайта fl.ru.
    Возвращает список dict: Задача, Ссылка (для обратной совместимости).
    """
    try:
        logger.info("Получаем RSS-ленту с %s", RSS_URL)
        feed = feedparser.parse(RSS_URL)
        if feed.bozo:
            logger.error("Ошибка при парсинге RSS-ленты.")
            return []
        if not feed.entries:
            logger.warning("Нет данных в RSS-ленте.")
            return []
        work = []
        for entry in feed.entries:
            task_name = entry.get("title", "Без названия")
            link = entry.get("link", "#")
            work.append({"Задача": task_name, "Ссылка": link})
        logger.info("Найдено %s задач(и) в RSS-ленте.", len(work))
        return work
    except Exception as e:
        logger.error("Произошла ошибка: %s", e)
        return []


def fetch_orders_for_db():
    """
    Парсит RSS и возвращает список заказов для записи в БД.
    Каждый элемент: fl_order_id, title, url, budget, published_ts (UTC timestamp для фильтра по времени).
    """
    try:
        feed = feedparser.parse(RSS_URL)
        if feed.bozo or not feed.entries:
            return []
        result = []
        for entry in feed.entries:
            title = entry.get("title", "Без названия")
            url = entry.get("link", "#")
            fl_order_id = _fl_order_id_from_url(url)
            if not fl_order_id:
                fl_order_id = url
            budget = ""
            summary = entry.get("summary", "") or ""
            budget_m = re.search(r"[Бб]юджет[:\s]*([^\s<]+)", summary, re.I)
            if budget_m:
                budget = budget_m.group(1).strip()
            # Время публикации (UTC) для фильтра «не старше 24ч» и «только новые»
            published_ts = 0
            if getattr(entry, "published_parsed", None):
                published_ts = calendar.timegm(entry.published_parsed)
            elif getattr(entry, "updated_parsed", None):
                published_ts = calendar.timegm(entry.updated_parsed)
            result.append({
                "fl_order_id": fl_order_id,
                "title": title,
                "url": url,
                "budget": budget,
                "published_ts": published_ts,
            })
        return result
    except Exception as e:
        logger.error("Ошибка fetch_orders_for_db: %s", e)
        return []

def main():
    tasks = parser()
    if tasks:
        for task in tasks:
            print(f"Задача: {task['Задача']}, Ссылка: {task['Ссылка']}")
    else:
        print("Задачи не найдены.")

if __name__ == '__main__':
    main()
