"""
Обработчики Telegram-бота: уведомления о заказах (fl.ru + Kwork), кнопки отклика и подтверждения.
Использует core.platforms для маркировки (DRY) и реестр обработчиков по платформе (Open/Closed).
"""
import asyncio
import logging
from typing import Callable, Awaitable

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

import parser as parser_module
from platforms import kwork_parser as kwork_parser_module
from db import models as db
from report.excel_reporter import append_row
from browser.automation import process_order as process_order_fl
from platforms.kwork_browser import process_order_kwork
from config.keywords import is_relevant_order
from bot.menu_handlers import _main_menu_keyboard
from core.platforms import get_prefix, get_display_name, normalize_platform
from core.parser_state import get_last_run_ts, set_last_run, filter_by_time

logger = logging.getLogger(__name__)
router = Router()

# Реестр обработчиков подготовки отклика по платформе (Open/Closed: новая биржа = новая запись)
ORDER_PROCESSORS: dict[str, Callable[[str, int], Awaitable[str]]] = {
    db.PLATFORM_FL_RU: process_order_fl,
    db.PLATFORM_KWORK: process_order_kwork,
}


def _keyboard_apply(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Откликнуться", callback_data=f"apply_{order_id}")]
    ])


def _keyboard_confirm_and_menu(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я отправил вручную -> Записать в отчет", callback_data=f"confirm_{order_id}")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="menu_main")],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🤖 Панель управления откликами (Python Developer)\n\nВыберите раздел:",
        reply_markup=_main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("apply_"))
async def on_apply(callback: CallbackQuery):
    """Подготовка отклика: выбор обработчика по платформе заказа (реестр — без if/else по биржам)."""
    try:
        order_id = int(callback.data.split("_", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка: неверный идентификатор заказа.", show_alert=True)
        return

    await callback.answer()
    order = await asyncio.to_thread(db.get_order_by_id, order_id)
    if not order:
        await callback.message.answer("Заказ не найден.")
        return
    if order["status"] not in (db.STATUS_NEW, db.STATUS_NOTIFIED):
        await callback.message.answer("Этот заказ уже обработан или в процессе.")
        return

    platform = normalize_platform(order.get("platform"))
    await asyncio.to_thread(db.update_order, order_id, status=db.STATUS_PROCESSING)
    await callback.message.answer(f"⏳ Открываю заказ в Firefox ({get_display_name(platform)}) и формирую отклик…")

    processor = ORDER_PROCESSORS.get(platform)
    if not processor:
        await callback.message.answer(f"Неизвестная платформа: {platform}.")
        await asyncio.to_thread(db.update_order, order_id, status=db.STATUS_NOTIFIED)
        return

    try:
        cover_letter = await processor(order["url"], order_id)
        await asyncio.to_thread(
            db.update_order,
            order_id,
            cover_letter=cover_letter,
            status=db.STATUS_READY_FOR_REVIEW,
        )
    except Exception as e:
        logger.exception("Ошибка при подготовке отклика для заказа %s: %s", order_id, e)
        await callback.message.answer(
            f"⚠️ Ошибка при подготовке отклика: {e}. Проверьте браузер и попробуйте снова."
        )
        await asyncio.to_thread(db.update_order, order_id, status=db.STATUS_NOTIFIED)
        return

    await callback.message.answer(
        "✅ Отклик подготовлен в Firefox!\n"
        "📝 Текст вставлен, резюме прикреплено.\n"
        "🖥 Вкладка открыта. Пожалуйста, проверьте текст, решите капчу (если есть) и нажмите кнопку «Отправить» на сайте вручную.\n"
        "👇 После отправки нажмите кнопку ниже, чтобы я записал данные в отчет.",
        reply_markup=_keyboard_confirm_and_menu(order_id),
    )


@router.callback_query(F.data.startswith("confirm_"))
async def on_confirm(callback: CallbackQuery):
    """Запись в отчёт по нажатию «Я отправил вручную» (с колонкой «Биржа»)."""
    try:
        order_id = int(callback.data.split("_", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка: неверный идентификатор заказа.", show_alert=True)
        return

    await callback.answer()
    order = await asyncio.to_thread(db.get_order_by_id, order_id)
    if not order:
        await callback.message.answer("Заказ не найден.")
        return
    if order["status"] != db.STATUS_READY_FOR_REVIEW:
        await callback.message.answer("Подтверждение уже учтено или заказ в другом статусе.")
        return

    await asyncio.to_thread(db.update_order, order_id, status=db.STATUS_CONFIRMED_MANUAL)
    platform_display = get_display_name(normalize_platform(order.get("platform")))
    await append_row(
        platform=platform_display,
        url=order["url"],
        cover_letter=order.get("cover_letter") or "",
        budget=order.get("budget") or "",
    )
    await callback.message.answer("✅ Данные записаны в отчёт.")


def _text_for_filter(order_data: dict, include_description: bool = False) -> str:
    """Текст для фильтра ключевых слов: заголовок + опционально описание (DRY)."""
    text = order_data.get("title", "")
    if include_description:
        text += " " + (order_data.get("description") or "")
    return text


async def run_parser_and_notify(bot, chat_id: int):
    """
    Парсит fl.ru и Kwork параллельно.
    Обе платформы: изначально — заказы не старше 24 ч; далее — только новые (новее последней проверки).
    Плюс фильтр по ключевым словам. Отправляет в Telegram с префиксами.
    """
    fl_orders, kwork_orders = await asyncio.gather(
        asyncio.to_thread(parser_module.fetch_orders_for_db),
        kwork_parser_module.fetch_orders_for_db(),
    )

    # Фильтр по времени для обеих платформ: 24ч при первом запуске, далее только новее last_run
    last_run_fl = await asyncio.to_thread(get_last_run_ts, "fl_ru")
    last_run_kwork = await asyncio.to_thread(get_last_run_ts, "kwork")
    fl_orders = filter_by_time(fl_orders, last_run_fl)
    kwork_orders = filter_by_time(kwork_orders, last_run_kwork)

    sources = [
        (fl_orders, db.PLATFORM_FL_RU, False),
        (kwork_orders, db.PLATFORM_KWORK, True),
    ]
    for orders, platform, use_description in sources:
        for o in orders:
            if not is_relevant_order(_text_for_filter(o, include_description=use_description)):
                continue
            await asyncio.to_thread(
                db.create_order,
                o["fl_order_id"],
                o["title"],
                o["url"],
                o.get("budget"),
                platform,
            )

    # Сохраняем время проверки для следующего цикла (только новые заказы в следующий раз)
    await asyncio.to_thread(set_last_run, "fl_ru")
    await asyncio.to_thread(set_last_run, "kwork")

    to_send = await asyncio.to_thread(db.get_new_orders)
    for order in to_send:
        prefix = get_prefix(normalize_platform(order.get("platform")))
        text = (
            f"{prefix} {order['title']}\n"
            f"💰 {order.get('budget') or '—'}\n"
            f"🔗 {order['url']}"
        )
        try:
            await bot.send_message(
                chat_id,
                text,
                reply_markup=_keyboard_apply(order["id"]),
            )
            await asyncio.to_thread(db.update_order, order["id"], status=db.STATUS_NOTIFIED)
        except Exception as e:
            logger.exception("Не удалось отправить заказ в Telegram: %s", e)
