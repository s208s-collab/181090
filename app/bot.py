from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from app.config import settings
from app.database import SessionLocal
from app.models import Order, OrderStatus


logger = logging.getLogger(__name__)
router = Router(name="orders")


def orders_keyboard() -> InlineKeyboardMarkup:
    """Кнопка под сообщением: она передаёт подписанные данные Mini App."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть заказы", web_app=WebAppInfo(url=settings.webapp_url))],
        ]
    )


def _has_access(message: Message) -> bool:
    return not settings.allowed_telegram_ids or bool(
        message.from_user and message.from_user.id in settings.allowed_telegram_ids
    )


async def _deny_if_needed(message: Message) -> bool:
    if _has_access(message):
        return False
    await message.answer("У этого аккаунта нет доступа к заказам. Обратитесь к владельцу.")
    return True


def _forwarded_name(message: Message) -> str | None:
    origin = message.forward_origin
    if not origin:
        return None
    sender_user = getattr(origin, "sender_user", None)
    if sender_user:
        return sender_user.full_name
    sender_chat = getattr(origin, "sender_chat", None)
    if sender_chat:
        return sender_chat.title
    return getattr(origin, "sender_user_name", None)


def create_order_from_message(message: Message) -> Order:
    text = (message.text or message.caption or "").strip()
    if not text:
        raise ValueError("В пересланном сообщении нет текста")

    author = message.from_user
    with SessionLocal() as session:
        order = Order(
            message_text=text,
            comment="",
            status=OrderStatus.ASSEMBLING.value,
            forwarded_from=_forwarded_name(message),
            created_by_telegram_id=author.id if author else None,
            created_by_name=author.full_name if author else None,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order


@router.message(CommandStart())
async def start(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    # Убираем старую reply-клавиатуру до отправки авторизованной Mini App-кнопки.
    await message.answer(
        "Здравствуйте! Перешлите мне сообщение с заказом — я добавлю его в общий список.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Кнопка «Открыть заказы» покажет все заказы и их статусы.",
        reply_markup=orders_keyboard(),
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    await message.answer(
        "1. Перешлите этому боту сообщение с заказом.\n"
        "2. Откройте «Открыть заказы».\n"
        "3. Меняйте статус и комментарий прямо в списке.",
        reply_markup=orders_keyboard(),
    )


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    """Помогает владельцу собрать ID сотрудников для ALLOWED_TELEGRAM_IDS."""
    if message.from_user:
        await message.answer(f"Ваш Telegram ID: {message.from_user.id}")


@router.message(F.forward_origin)
async def forwarded_order(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    if not (message.text or message.caption):
        await message.answer("В этом пересланном сообщении нет текста. Перешлите заказ текстом или с подписью.")
        return
    order = create_order_from_message(message)
    await message.answer(
        f"Заказ №{order.order_number} добавлен со статусом «{OrderStatus.ASSEMBLING.value}».\n"
        "Откройте список, чтобы добавить комментарий или изменить статус.",
        reply_markup=orders_keyboard(),
    )


@router.message()
async def regular_message(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    await message.answer(
        "Перешлите мне сообщение с заказом — я сохраню его. Затем нажмите «Открыть заказы».",
        reply_markup=orders_keyboard(),
    )


async def prepare_bot() -> tuple[Bot, Dispatcher]:
    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Начать работу"),
                BotCommand(command="help", description="Как добавить заказ"),
                BotCommand(command="myid", description="Показать мой Telegram ID"),
            ]
        )
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Открыть заказы", web_app=WebAppInfo(url=settings.webapp_url))
        )
    except Exception:
        await bot.session.close()
        raise
    return bot, dispatcher


async def run_bot(bot: Bot, dispatcher: Dispatcher) -> None:
    """Запускает long polling; подходит для одного постоянно работающего сервиса."""
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Telegram bot started at %s", datetime.now().isoformat())
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
