"""
Главное меню и навигация по статусам (DRY): фиксированная Reply-клавиатура, списки — inline.
"""
import asyncio
import logging
from typing import List, Optional, Tuple

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramBadRequest

from db import models as db
from core.platforms import get_prefix, normalize_platform

logger = logging.getLogger(__name__)
router = Router()

PAGE_SIZE = 8
MAIN_MENU_TITLE = "🤖 Панель управления откликами (Python Developer)\n\nВыберите раздел:"

# Тексты кнопок главного меню (Reply-клавиатура)
BTN_NEW = "📥 Новые заказы"
BTN_READY = "⏳ Ожидают отправки"
BTN_ARCH = "✅ Архив откликов"
BTN_ALL = "📋 Все заказы"
BTN_REFRESH = "🔄 Обновить список"

# (status или None для all, заголовок, сообщение при пустоте)
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
    "all": (None, "📋 Все заказы", "Нет заказов в базе."),
}


async def _edit_message_safe(message, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    """Редактирует сообщение; если текст и клавиатура не изменились — игнорирует ошибку Telegram."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


def _main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Фиксированная клавиатура главного меню (всегда видна внизу)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NEW), KeyboardButton(text=BTN_READY)],
            [KeyboardButton(text=BTN_ARCH), KeyboardButton(text=BTN_ALL)],
            [KeyboardButton(text=BTN_REFRESH)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


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


def _text_to_section(text: str) -> Optional[str]:
    """Маппинг текста Reply-кнопки на section."""
    if text == BTN_NEW:
        return "new"
    if text == BTN_READY:
        return "ready"
    if text == BTN_ARCH:
        return "arch"
    if text == BTN_ALL:
        return "all"
    return None


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
    if section == "all":
        # Одна кнопка на заказ: Apply / Confirm или пустая строка (архив)
        result = []
        for o in orders:
            st = o.get("status", "")
            if st == db.STATUS_READY_FOR_REVIEW:
                result.append([InlineKeyboardButton(text="✅ Я отправил вручную -> Записать в отчет", callback_data=f"confirm_{o['id']}")])
            elif st in (db.STATUS_NEW, db.STATUS_NOTIFIED):
                result.append([InlineKeyboardButton(text=f"✍️ Подготовить отклик | {(o.get('title') or '')[:30]}...", callback_data=f"apply_{o['id']}")])
            else:
                result.append([InlineKeyboardButton(text="📦 В архиве", callback_data="noop")])
        return result
    return []  # архив — без кнопок действий


async def _build_list_content_and_keyboard(
    section: str,
    page: int,
) -> Tuple[str, InlineKeyboardMarkup]:
    """Строит текст списка и inline-клавиатуру. section: new | ready | arch | all."""
    if section not in MENU_SECTIONS:
        section = "new"
    status_or_none, title, empty_msg = MENU_SECTIONS[section]

    if section == "all":
        total = await asyncio.to_thread(db.count_all_orders)
    else:
        total = await asyncio.to_thread(db.count_orders_by_status, status_or_none)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    offset = page * PAGE_SIZE

    if section == "all":
        orders = await asyncio.to_thread(db.get_all_orders, PAGE_SIZE, offset)
    else:
        orders = await asyncio.to_thread(db.get_orders_by_status, status_or_none, PAGE_SIZE, offset)
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
    return "\n".join(lines), keyboard


async def _render_status_list(callback: CallbackQuery, section: str) -> None:
    """Редактирует сообщение списком (из inline-пагинации)."""
    _, page = _parse_callback_page(callback.data)
    text, keyboard = await _build_list_content_and_keyboard(section, page)
    await _edit_message_safe(callback.message, text, keyboard)


async def _send_status_list(message: Message, section: str, page: int = 0) -> None:
    """Отправляет новое сообщение со списком (из Reply-кнопки главного меню)."""
    text, keyboard = await _build_list_content_and_keyboard(section, page)
    await message.answer(text, reply_markup=keyboard)


# Обработчики меню

@router.callback_query(F.data == "menu_main")
async def on_menu_main_callback(callback: CallbackQuery):
    """Inline «В меню»: убираем inline-кнопки, показываем заголовок. Reply-клавиатура остаётся."""
    await callback.answer()
    try:
        await callback.message.edit_text(MAIN_MENU_TITLE, reply_markup=None)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


@router.callback_query(F.data == "noop")
async def on_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "menu_refresh")
async def on_menu_refresh_callback(callback: CallbackQuery):
    await callback.answer("Список обновлён")
    try:
        await callback.message.edit_text(MAIN_MENU_TITLE, reply_markup=None)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


# Reply-кнопки главного меню (фиксированная клавиатура)
@router.message(F.text.in_([BTN_NEW, BTN_READY, BTN_ARCH, BTN_ALL]))
async def on_main_menu_reply(message: Message):
    """Обработка нажатий кнопок главного меню."""
    section = _text_to_section(message.text)
    if section:
        await _send_status_list(message, section)


@router.message(F.text == BTN_REFRESH)
async def on_refresh_reply(message: Message):
    """Обновить список — возврат к главному экрану."""
    await message.answer(MAIN_MENU_TITLE)


# Inline-пагинация (при навигации внутри списков)
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


@router.callback_query(F.data.startswith("menu_all_"))
async def on_list_all(callback: CallbackQuery):
    await callback.answer()
    await _render_status_list(callback, "all")
