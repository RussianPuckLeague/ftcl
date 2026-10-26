import asyncio
import os
import sys
import time
from typing import Set

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatMemberUpdated,
)

def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"❌ Не задана обязательная переменная окружения: {name}", file=sys.stderr)
        sys.exit(1)
    return value

TOKEN = env_required("BOT_TOKEN")
ADMIN_LOGIN = env_required("ADMIN_LOGIN")
ADMIN_PASSWORD = env_required("ADMIN_PASSWORD")

CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/")
SITE_URL = os.getenv("SITE_URL", "https://example.com")

bot = Bot(TOKEN)
dp = Dispatcher()

# --- Состояния админки ---
admin_steps: dict[int, str] = {}
admin_sessions: set[int] = set()
bound_channels: dict[int, int] = {}  # admin_user_id -> channel_id

# --- «Копилка» известных боту пользователей ---
# Ключ: channel_id, значение: множество user_id
# В реальном проекте это должна быть БД, но для демо — память.
known_members: dict[int, Set[int]] = {}


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Аналитика матчей"), KeyboardButton(text="🥅 Лучшие вратари")],
            [KeyboardButton(text="🏒 Лучшие бомбардиры"), KeyboardButton(text="🎯 Лучшие снайперы")],
            [KeyboardButton(text="🔮 Шансы на победу"), KeyboardButton(text="🏆 Турнирная таблица")],
            [KeyboardButton(text="📜 Рекорды"), KeyboardButton(text="🎲 Бинго")],
            [KeyboardButton(text="🛡 Команды"), KeyboardButton(text="🔎 Найти игрока")],
            [KeyboardButton(text="📣 Telegram-канал лиги"), KeyboardButton(text="🌐 Сайт лиги")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел 👇",
    )


@dp.message(Command("start"))
async def start(message: Message):
    user = message.from_user
    name = user.first_name or "игрок"
    await message.answer(
        f"🏒 <b>Добро пожаловать в лигу, {name}!</b>\n\n"
        "👤 <b>Ваш профиль</b>\n"
        "━━━━━━━━━━━━━━\n"
        "🥅 Голы: <b>—</b>\n"
        "🅰️ Ассисты: <b>—</b>\n"
        "⭐ Очки: <b>—</b>\n\n"
        "🛡 <b>Статистика защитника</b>\n"
        "💥 Хиты: <b>—</b>\n"
        "🔄 Перехваты: <b>—</b>\n"
        "🚫 Блоки: <b>—</b>\n\n"
        "👕 Команда: <b>empty</b>\n\n"
        "Выберите нужный раздел в меню ниже 👇",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


@dp.message(Command("adminka6767"))
async def admin_login(message: Message):
    admin_steps[message.from_user.id] = "login"
    await message.answer("🔐 <b>Вход в панель администратора</b>\n\nВведите логин:", parse_mode="HTML")


# --- СБОР ID: пользователь вступил в канал ---
@dp.chat_member()
async def on_chat_member_updated(update: ChatMemberUpdated):
    """
    Срабатывает, когда меняется статус участника в канале/группе.
    Если бот — админ, он получает это обновление при вступлении.
    """
    chat_id = update.chat.id
    user_id = update.new_chat_member.user.id

    # Нас интересуют только те, кто стал участником (или вернулся)
    status = update.new_chat_member.status
    if status in ("member", "restricted", "administrator", "creator"):
        known_members.setdefault(chat_id, set()).add(user_id)


# --- СБОР ID: пользователь написал в чат ---
@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}))
async def collect_from_messages(message: Message):
    """
    Любое сообщение в группе/канале (если бот его видит) добавляет автора в копилку.
    В каналах бот видит только посты админов, но в группах — всех.
    """
    if message.from_user and not message.from_user.is_bot:
        known_members.setdefault(message.chat.id, set()).add(message.from_user.id)
    # Не прерываем обработку, пусть идут другие хэндлеры
    # (в aiogram 3 нужно явно не возвращать, чтобы цепочка продолжилась,
    #  но здесь мы просто ничего не делаем — управление пойдёт дальше)


@dp.message(F.forward_from_chat)
async def receive_forwarded_channel(message: Message):
    user_id = message.from_user.id
    if user_id not in admin_sessions:
        return

    channel = message.forward_from_chat
    if channel is None or channel.id is None:
        await message.answer("❌ Не удалось определить канал.")
        return

    try:
        member = await bot.get_chat_member(channel.id, bot.id)
        if member.status not in ("administrator", "creator"):
            await message.answer(
                "⚠️ Бот пока не администратор этого канала.\n"
                "Добавьте его в администраторы и попробуйте ещё раз."
            )
            return
        # Проверяем право на блокировку
        if not getattr(member, "can_restrict_members", False):
            await message.answer(
                "⚠️ У бота нет права «Блокировка пользователей» в этом канале.\n"
                "Выдайте это право в настройках администратора."
            )
            return

        bound_channels[user_id] = channel.id
        known_members.setdefault(channel.id, set())  # инициализируем копилку
        await message.answer(
            f"✅ Канал <b>{channel.title}</b> успешно привязан!\n"
            f"👥 Известных боту участников: <b>{len(known_members[channel.id])}</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Не получилось проверить канал.\n{e}")


# --- МАССОВЫЙ БАН (вызывается из админки) ---
@dp.callback_query(F.data == "reset_info")
async def reset_info(callback):
    user_id = callback.from_user.id
    if user_id not in admin_sessions:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    channel_id = bound_channels.get(user_id)
    if not channel_id:
        await callback.answer("Сначала привяжите канал", show_alert=True)
        return

    members = known_members.get(channel_id, set())
    if not members:
        await callback.answer("Бот ещё не знает ни одного участника этого канала", show_alert=True)
        return

    # Подтверждение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, забанить", callback_data="confirm_ban_all")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_ban")],
    ])
    await callback.message.answer(
        f"⚠️ <b>Подтверждение</b>\n\n"
        f"Будет забанено <b>{len(members)}</b> известных боту пользователей в канале.\n"
        f"Они будут исключены из подписчиков и не смогут вернуться по ссылке, "
        f"пока вы их не разбаните.\n\n"
        f"Продолжить?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "cancel_ban")
async def cancel_ban(callback):
    await callback.message.edit_text("❌ Обнуление отменено.")
    await callback.answer()


@dp.callback_query(F.data == "confirm_ban_all")
async def confirm_ban_all(callback):
    user_id = callback.from_user.id
    if user_id not in admin_sessions:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    channel_id = bound_channels.get(user_id)
    members = list(known_members.get(channel_id, set()))

    await callback.message.edit_text(
        f"⏳ Начинаю блокировку <b>{len(members)}</b> пользователей…\n"
        f"Это может занять время. Бот будет делать паузы, чтобы не превысить лимиты Telegram.",
        parse_mode="HTML",
    )
    await callback.answer()

    banned, failed, skipped = 0, 0, 0
    for i, member_id in enumerate(members, 1):
        try:
            # Проверяем, не является ли пользователь админом/создателем — их банить нельзя
            member_info = await bot.get_chat_member(channel_id, member_id)
            if member_info.status in ("administrator", "creator"):
                skipped += 1
                continue

            await bot.ban_chat_member(chat_id=channel_id, user_id=member_id)
            banned += 1

            # Обновление прогресса каждые 20 банов (чтобы не спамить редактированием)
            if i % 20 == 0:
                try:
                    await callback.message.edit_text(
                        f"⏳ Прогресс: {i}/{len(members)}\n✅ Забанено: {banned} | ⏭ Пропущено: {skipped} | ❌ Ошибок: {failed}",
                    )
                except Exception:
                    pass  # не критично, если не удалось обновить сообщение

            # Пауза между запросами. 0.5 сек может быть мало; безопаснее 1 сек.
            await asyncio.sleep(1.0)

        except TelegramRetryAfter as e:
            # Telegram сказал: «подожди N секунд»
            wait = e.retry_after
            await callback.message.answer(f"⏳ Telegram просит подождать {wait} сек. Продолжаю после паузы…")
            await asyncio.sleep(wait)
            # Пробуем ещё раз этого же пользователя
            try:
                await bot.ban_chat_member(chat_id=channel_id, user_id=member_id)
                banned += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
            # Небольшая пауза даже при ошибке, чтобы не долбить API
            await asyncio.sleep(0.5)

    # Очищаем копилку после обработки
    known_members[channel_id] = set()

    await callback.message.answer(
        f"✅ <b>Готово</b>\n\n"
        f"Забанено: <b>{banned}</b>\n"
        f"Пропущено (админы): <b>{skipped}</b>\n"
        f"Ошибок: <b>{failed}</b>\n\n"
        f"⚠️ Напоминание: это бан, а не просто удаление. Пользователи не смогут вернуться, "
        f"пока вы не разбаните их через <code>/unban</code> (или вручную в Telegram).",
        parse_mode="HTML",
    )


@dp.message(F.text)
async def handle_text(message: Message):
    if message.forward_from_chat is not None:
        return

    user_id = message.from_user.id
    text = message.text.strip()
    step = admin_steps.get(user_id)

    if step == "login":
        if text == ADMIN_LOGIN:
            admin_steps[user_id] = "password"
            await message.answer("✅ Логин принят!\n\nВведите пароль:")
        else:
            admin_steps.pop(user_id, None)
            await message.answer("❌ Неверный логин. Попробуйте снова.")
        return

    if step == "password":
        admin_steps.pop(user_id, None)
        if text == ADMIN_PASSWORD:
            admin_sessions.add(user_id)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📣 Привязать канал", callback_data="bind_channel")],
                [InlineKeyboardButton(text="🧹 Обнуление канала", callback_data="reset_info")],
            ])
            await message.answer(
                "✅ <b>Вы вошли в панель администратора</b>\n\nВыберите действие:",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        else:
            await message.answer("❌ Неверный пароль. Попробуйте снова.")
        return

    if text == "📣 Telegram-канал лиги":
        await message.answer(f"📣 <b>Канал лиги:</b>\n{CHANNEL_URL}", parse_mode="HTML")
        return
    if text == "🌐 Сайт лиги":
        await message.answer(f"🌐 <b>Сайт лиги:</b>\n{SITE_URL}", parse_mode="HTML")
        return

    sections = {
        "📊 Аналитика матчей", "🥅 Лучшие вратари", "🏒 Лучшие бомбардиры",
        "🎯 Лучшие снайперы", "🔮 Шансы на победу", "🏆 Турнирная таблица",
        "📜 Рекорды", "🎲 Бинго", "🛡 Команды", "🔎 Найти игрока",
    }
    if text in sections:
        await message.answer("⚠️ Произошла ошибка, попробуйте позже…\n\nМы уже работаем над этим разделом 🔧")


@dp.callback_query(F.data == "bind_channel")
async def bind_channel(callback):
    if callback.from_user.id not in admin_sessions:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.message.answer(
        "📣 <b>Привязка канала</b>\n\n"
        "Перешлите сюда сообщение из нужного канала.\n"
        "Убедитесь, что бот добавлен в канал администратором с правом «Блокировка пользователей» ✅",
        parse_mode="HTML",
    )
    await callback.answer()


async def main():
    print("🤖 Бот запускается...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
