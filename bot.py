import asyncio
import os
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
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

# Временное хранение (сбрасывается при перезапуске).
admin_steps: dict[int, str] = {}
admin_sessions: set[int] = set()
bound_channels: dict[int, int] = {}


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
    await message.answer(
        "🔐 <b>Вход в панель администратора</b>\n\nВведите логин:",
        parse_mode="HTML",
    )


# ⚠️ ВАЖНО: этот хэндлер должен идти ДО общего @dp.message(F.text),
# иначе пересланные из канала сообщения с текстом будут перехватываться меню.
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

        bound_channels[user_id] = channel.id
        await message.answer(
            f"✅ Канал <b>{channel.title}</b> успешно привязан!",
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(
            "❌ Не получилось проверить канал.\n"
            "Проверьте, что бот добавлен туда администратором."
        )


@dp.message(F.text)
async def handle_text(message: Message):
    # пропускаем пересланные из каналов сообщения — их обрабатывает хэндлер выше
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

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📣 Привязать канал", callback_data="bind_channel")],
                    [InlineKeyboardButton(text="🧹 Обнуление лиги", callback_data="reset_info")],
                ]
            )

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
        "📊 Аналитика матчей",
        "🥅 Лучшие вратари",
        "🏒 Лучшие бомбардиры",
        "🎯 Лучшие снайперы",
        "🔮 Шансы на победу",
        "🏆 Турнирная таблица",
        "📜 Рекорды",
        "🎲 Бинго",
        "🛡 Команды",
        "🔎 Найти игрока",
    }

    if text in sections:
        await message.answer(
            "⚠️ Произошла ошибка, попробуйте позже…\n\n"
            "Мы уже работаем над этим разделом 🔧"
        )


@dp.callback_query(F.data == "bind_channel")
async def bind_channel(callback):
    if callback.from_user.id not in admin_sessions:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.message.answer(
        "📣 <b>Привязка канала</b>\n\n"
        "Перешлите сюда сообщение из нужного канала.\n"
        "Убедитесь, что бот добавлен в канал администратором ✅",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "reset_info")
async def reset_info(callback):
    if callback.from_user.id not in admin_sessions:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.message.answer(
        "ℹ️ <b>Ограничения Telegram</b>\n\n"
        "Бот не может получить полный список подписчиков канала "
        "или автоматически удалить их всех. Также Bot API не позволяет "
        "просмотреть и удалить всю историю канала.\n\n"
        "🧹 Удаление участников и старых публикаций нужно выполнить вручную "
        "через настройки канала.",
        parse_mode="HTML",
    )
    await callback.answer()


async def main():
    print("🤖 Бот запускается...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
