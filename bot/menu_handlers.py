"""
Главное меню и навигация по статусам (DRY): общая логика пагинации и рендеринга списков.
"""
import asyncio
import logging
from typing import List, Tuple

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from db import models as db
from core.platforms import get_prefix, normalize_platform

logger = logging.getLogger(__name__)
router = Router()

PAGE_SIZE = 8
MAIN_MENU_TITLE = "🤖 Панель управления откликами (Python Developer)\n\nВыберите раздел:"

# (status, заголовок списка, сообщение при пустоте)
MENU_SECTIONS = {
    "new": (
        db.STATUS_NEW,
        "📥 Новые заказы",
        "Нет заказов со статусом «Новые».",
    ),
    "ready": (
        db.STATUS_READY_FOR_REVIEW,
        "⏳ Ожидают отправки",
        "Нет заказов, ожидающих ручной отправки.",
    ),
    "arch": (
        db.STATUS_CONFIRMED_MANUAL,
        "✅ Архив откликов",
        "Архив пуст.",
    ),
}


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Новые заказы", callback_data="menu_new_0")],
        [InlineKeyboardButton(text="⏳ Ожидают отправки", callback_data="menu_ready_0")],
        [InlineKeyboardButton(text="✅ Архив откликов", callback_data="menu_arch_0")],
        [InlineKeyboardButton(text="🔄 Обновить список", callback_data="menu_refresh")],
    ])


def _pagination_keyboard(
    status_key: str,
    page: int,
    total_pages: int,
    has_items: bool,
) -> InlineKeyboardMarkup:
    """Кнопки пагинации и «В меню» (одна реализация для всех разделов)."""
    buttons = []
    if has_items and total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"menu_{status_key}_{page - 1}"))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ▶", callback_data=f"menu_{status_key}_{page + 1}"))
        if row:
            buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_order_card(order: dict, with_budget: bool = True) -> str:
    """Одна карточка заказа с префиксом биржи (использует core.platforms)."""
    prefix = get_prefix(normalize_platform(order.get("platform")))
    title = (order.get("title") or "Без названия")[:80]
    line = f"{prefix} {title}"
    if with_budget and order.get("budget"):
        line += f" | {order['budget']}"
    return line


def _parse_callback_page(callback_data: str) -> Tuple[str, int]:
    """Извлекает (section, page) из callback_data вида menu_new_0, menu_ready_1 и т.д."""
    parts = callback_data.split("_")
    if len(parts) >= 3:
        try:
            return parts[1], int(parts[2])
        except (IndexError, ValueError):
            pass
    return "new", 0


def _build_row_buttons_for_section(orders: list, section: str) -> List[List[InlineKeyboardButton]]:
    """Строит кнопки для каждой строки списка в зависимости от раздела (DRY)."""
    if section == "new":
        return [
            [InlineKeyboardButton(text=f"✍️ Подготовить отклик | {o['title'][:30]}...", callback_data=f"apply_{o['id']}")]
            for o in orders
        ]
    if section == "ready":
        return [
            [InlineKeyboardButton(text="✅ Я отправил вручную -> Записать в отчет", callback_data=f"confirm_{o['id']}")]
            for o in orders
        ]
    return []  # архив — без кнопок действий


async def _render_status_list(callback: CallbackQuery, section: str) -> None:
    """
    Общая логика рендеринга списка по статусу: пагинация, карточки, кнопки.
    section: "new" | "ready" | "arch".
    """
    if section not in MENU_SECTIONS:
        section = "new"
    status, title, empty_msg = MENU_SECTIONS[section]
    _, page = _parse_callback_page(callback.data)

    total = await asyncio.to_thread(db.count_orders_by_status, status)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    offset = page * PAGE_SIZE

    orders = await asyncio.to_thread(db.get_orders_by_status, status, PAGE_SIZE, offset)
    lines = [f"{title}\n"]
    if not orders:
        lines.append(empty_msg)
    else:
        with_budget = section != "ready"
        for o in orders:
            lines.append(_format_order_card(o, with_budget=with_budget))

    row_buttons = _build_row_buttons_for_section(orders, section)
    pagination = _pagination_keyboard(section, page, total_pages, bool(orders)).inline_keyboard
    keyboard = InlineKeyboardMarkup(inline_keyboard=row_buttons + pagination)

    await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)


# Обработчики меню

@router.callback_query(F.data == "menu_main")
async def on_menu_main(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(MAIN_MENU_TITLE, reply_markup=_main_menu_keyboard())


@router.callback_query(F.data == "menu_refresh")
async def on_menu_refresh(callback: CallbackQuery):
    await callback.answer("Список обновлён")
    await on_menu_main(callback)


@router.callback_query(F.data.startswith("menu_new_"))
async def on_list_new(callback: CallbackQuery):
    await callback.answer()
    await _render_status_list(callback, "new")


@router.callback_query(F.data.startswith("menu_ready_"))
async def on_list_ready(callback: CallbackQuery):
    await callback.answer()
    await _render_status_list(callback, "ready")


@router.callback_query(F.data.startswith("menu_arch_"))
async def on_list_archive(callback: CallbackQuery):
    await callback.answer()
    await _render_status_list(callback, "arch")
