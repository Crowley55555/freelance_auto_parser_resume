"""
Парсер заказов Kwork: список проектов подгружается через JavaScript, поэтому используем Playwright.
Открываем страницу в headless Chromium, извлекаем данные и дату публикации для фильтра по времени.

Требуется установка браузера для Playwright (если ещё не ставили Chromium):
    playwright install chromium
"""
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

KWORK_PROJECTS_URL = "https://kwork.ru/projects?fc=39"
PROJECT_LINK_PATTERN = re.compile(r"/projects/(\d+)")


def _kwork_order_id_from_url(url: str) -> str:
    """Извлекает идентификатор заказа из URL Kwork."""
    if not url:
        return ""
    m = PROJECT_LINK_PATTERN.search(url)
    return m.group(1) if m else url


def _parse_kwork_date(date_text: str, datetime_attr: Optional[str]) -> int:
    """
    Преобразует дату с Kwork в Unix timestamp (UTC).
    Приоритет: атрибут datetime (ISO), иначе текст вида «N мин назад», «вчера» и т.д.
    """
    now = datetime.now(timezone.utc)
    if datetime_attr:
        try:
            dt = datetime.fromisoformat(datetime_attr.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except (ValueError, TypeError):
            pass
    if not date_text:
        return int(now.timestamp())
    text = date_text.strip().lower()
    # Минуты назад
    m = re.search(r"(\d+)\s*мин", text)
    if m:
        return int((now - timedelta(minutes=int(m.group(1)))).timestamp())
    # Часов назад
    m = re.search(r"(\d+)\s*час", text)
    if m:
        return int((now - timedelta(hours=int(m.group(1)))).timestamp())
    # Дней назад
    m = re.search(r"(\d+)\s*дн", text)
    if m:
        return int((now - timedelta(days=int(m.group(1)))).timestamp())
    if "вчера" in text or "вчера" in date_text:
        return int((now - timedelta(days=1)).timestamp())
    if "сегодня" in text:
        return int(now.timestamp())
    # По умолчанию считаем свежим (не отфильтруем)
    return int(now.timestamp())


async def fetch_orders_for_db() -> List[Dict[str, Any]]:
    """
    Загружает страницу проектов Kwork в headless браузере (контент подгружается по JS),
    ждёт появления списка, извлекает заголовок, ссылку, бюджет и описание из DOM.
    """
    result: List[Dict[str, Any]] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                locale="ru-RU",
                user_agent="Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0",
            )
            page = await context.new_page()

            await page.goto(KWORK_PROJECTS_URL, wait_until="domcontentloaded", timeout=20000)
            # Ждём появления ссылок на проекты (список рендерится JS)
            try:
                await page.wait_for_selector(
                    "a[href*='/projects/']",
                    timeout=15000,
                    state="attached",
                )
            except Exception as e:
                logger.warning("Kwork: не дождались появления списка проектов: %s", e)
                await browser.close()
                return []

            await page.wait_for_load_state("networkidle", timeout=10000)

            # Извлекаем данные через JS: ссылки, карточка, бюджет, описание и дата публикации
            raw_items = await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll("a[href*='/projects/']"));
                    const seen = new Set();
                    const items = [];
                    for (const a of links) {
                        const href = a.href || a.getAttribute('href') || '';
                        if (!/\\/projects\\/\\d+/.test(href) || seen.has(href)) continue;
                        seen.add(href);
                        const card = a.closest('[class*="card"], [class*="Card"], [class*="item"], [class*="Item"], [data-id], article, .w-') || a.parentElement;
                        const cardText = card ? card.innerText : a.innerText;
                        const title = (a.textContent || cardText || '').trim().slice(0, 500);
                        const priceMatch = cardText.match(/\\d+\\s*₽|\\d+\\s*руб|\\$\\s*\\d+|\\d+\\s*\\$/i);
                        const budget = priceMatch ? priceMatch[0].trim() : '';
                        let dateText = '';
                        let datetimeAttr = null;
                        const timeEl = card ? card.querySelector('time[datetime]') : null;
                        if (timeEl) {
                            datetimeAttr = timeEl.getAttribute('datetime');
                            dateText = timeEl.innerText || '';
                        }
                        if (!dateText && card) {
                            const all = card.querySelectorAll('[class*="time"], [class*="date"], [class*="Time"], [class*="Date"]');
                            for (const el of all) {
                                const t = (el.innerText || '').trim();
                                if (/назад|минут|час|дн|вчера|сегодня|\\d{1,2}:\\d{2}/.test(t)) { dateText = t; break; }
                            }
                        }
                        if (!dateText && card) dateText = cardText.slice(0, 300);
                        items.push({ href, title, budget, description: cardText.slice(0, 1000), dateText, datetimeAttr });
                    }
                    return items;
                }
            """)

            await browser.close()

            for item in raw_items:
                href = item.get("href", "")
                if not href or not PROJECT_LINK_PATTERN.search(href):
                    continue
                if not href.startswith("http"):
                    href = "https://kwork.ru" + (href if href.startswith("/") else "/" + href)
                order_id = _kwork_order_id_from_url(href) or href
                published_ts = _parse_kwork_date(
                    item.get("dateText") or "",
                    item.get("datetimeAttr"),
                )
                result.append({
                    "fl_order_id": order_id,
                    "title": (item.get("title") or "Без названия").strip()[:500],
                    "url": href,
                    "budget": (item.get("budget") or "").strip(),
                    "description": (item.get("description") or "").strip()[:2000],
                    "published_ts": published_ts,
                })

    except Exception as e:
        logger.exception("Kwork: ошибка при парсинге: %s", e)
        return []

    logger.info("Kwork: найдено %s заказов", len(result))
    return result
