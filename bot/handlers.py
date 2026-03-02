"""
Обработчики Telegram-бота: уведомления о заказах, кнопка «Откликнуться» и «Я отправил вручную -> Записать в отчёт».
Единый сценарий: бот только заполняет форму; запись в отчёт — только по нажатию кнопки подтверждения.
"""
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

import parser as parser_module
from db import models as db
from report.excel_reporter import append_row
from browser.automation import process_order

logger = logging.getLogger(__name__)
router = Router()


def _keyboard_apply(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Откликнуться", callback_data=f"apply_{order_id}")]
    ])


def _keyboard_confirm(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я отправил вручную -> Записать в отчет", callback_data=f"confirm_{order_id}")]
    ])


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Здравствуйте. Бот для полуавтоматических откликов на fl.ru. "
        "Новые заказы будут приходить сюда с кнопкой «Откликнуться». "
        "Бот заполняет форму; отправку на сайте вы нажимаете вручную."
    )


@router.callback_query(F.data.startswith("apply_"))
async def on_apply(callback: CallbackQuery):
    """Пользователь нажал «✍️ Откликнуться» — открываем заказ в Firefox, заполняем форму, не отправляем."""
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

    await asyncio.to_thread(db.update_order, order_id, status=db.STATUS_PROCESSING)
    await callback.message.answer("⏳ Открываю заказ в Firefox и формирую отклик…")

    try:
        cover_letter = await process_order(order["url"], order_id)
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
        reply_markup=_keyboard_confirm(order_id),
    )


@router.callback_query(F.data.startswith("confirm_"))
async def on_confirm(callback: CallbackQuery):
    """Пользователь нажал «✅ Я отправил вручную -> Записать в отчет» — записываем в Excel и обновляем статус в БД."""
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
    cover_letter = order.get("cover_letter") or ""
    await append_row(
        url=order["url"],
        cover_letter=cover_letter,
        budget=order.get("budget") or "",
    )
    await callback.message.answer("✅ Данные записаны в отчёт.")


async def run_parser_and_notify(bot, chat_id: int):
    """
    Запускает парсер RSS, создаёт заказы в БД, отправляет в Telegram только новые (status=new)
    и переводит их в status=notified.
    """
    orders_from_rss = await asyncio.to_thread(parser_module.fetch_orders_for_db)
    for o in orders_from_rss:
        await asyncio.to_thread(db.create_order, o["fl_order_id"], o["title"], o["url"], o.get("budget"))

    to_send = await asyncio.to_thread(db.get_new_orders)
    for order in to_send:
        text = (
            f"🔥 Новый заказ: {order['title']}\n"
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
