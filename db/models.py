"""
Инициализация SQLite и работа с таблицей заказов.
"""
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "orders.db"
STATUS_NEW = "new"
STATUS_NOTIFIED = "notified"  # уведомление отправлено в Telegram
STATUS_PROCESSING = "processing"
STATUS_READY_FOR_REVIEW = "ready_for_review"  # бот заполнил форму, ждёт ручной отправки пользователем
STATUS_CONFIRMED_MANUAL = "confirmed_manual"  # пользователь подтвердил в боте, что отправил вручную


def get_connection() -> sqlite3.Connection:
    """Возвращает подключение к БД (создаёт файл и директорию при необходимости)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создаёт таблицу orders, если её нет."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fl_order_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                budget TEXT,
                cover_letter TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_fl_order_id ON orders(fl_order_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)"
        )
        conn.commit()
        logger.info("База данных инициализирована: %s", DB_PATH)
    finally:
        conn.close()


def create_order(
    fl_order_id: str,
    title: str,
    url: str,
    budget: Optional[str] = None,
) -> int:
    """Создаёт запись заказа. Возвращает id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO orders (fl_order_id, title, url, budget, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (fl_order_id, title, url, budget or "", STATUS_NEW, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # уже есть такой fl_order_id
        cur = conn.execute("SELECT id FROM orders WHERE fl_order_id = ?", (fl_order_id,))
        row = cur.fetchone()
        return row["id"] if row else 0
    finally:
        conn.close()


def get_order_by_id(order_id: int) -> Optional[dict]:
    """Возвращает заказ по id или None."""
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_order_by_fl_id(fl_order_id: str) -> Optional[dict]:
    """Возвращает заказ по fl_order_id или None."""
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM orders WHERE fl_order_id = ?", (fl_order_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_order(
    order_id: int,
    *,
    cover_letter: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    """Обновляет поля заказа."""
    conn = get_connection()
    try:
        if cover_letter is not None:
            conn.execute("UPDATE orders SET cover_letter = ? WHERE id = ?", (cover_letter, order_id))
        if status is not None:
            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        conn.commit()
    finally:
        conn.close()


def get_new_orders() -> list:
    """Возвращает список заказов со статусом new (для парсера — какие ещё не показывали)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC",
            (STATUS_NEW,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
