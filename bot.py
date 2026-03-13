import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from bd import Database
import os

TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
TARGET_TOPIC_ID = os.getenv("TARGET_TOPIC_ID")

if not TARGET_CHAT_ID or TARGET_TOPIC_ID:
    raise Exception("TARGET_CHAT_ID and TARGET_TOPIC_ID must be set")

POINTS_BY_VALUE = POINTS_BY_VALUE = {i: 1 for i in range(1, 65)}
SPECIAL_VALUES = {
    22: 5,   # 🍇🍇🍇
    1: 10,   # 🍾🍾🍾
    43: 5,   # 🍋🍋🍋
    64: 20,  # 7️⃣7️⃣7️⃣
}

logger = logging.getLogger(__name__)

db = Database()
dp = Dispatcher()


#ОБРАБОТЧИКИ
async def handle_dice(message: types.Message):
    # Проверяем чат и топик
    if message.chat.id != TARGET_CHAT_ID:
        return
    if message.message_thread_id != TARGET_TOPIC_ID:
        return
    if not message.dice or message.dice.emoji != "🎰":
        return

    value = message.dice.value
    points = POINTS_BY_VALUE.get(value, 1)

    if message.from_user:  # безопасная проверка
        db.add_user(message.from_user)
        match value:
            case 22:
                db.add_spin(message.from_user.id, value, points*5)
            case 1:
                db.add_spin(message.from_user.id, value, points*10)
            case 43:
                db.add_spin(message.from_user.id, value, points*5)
            case 64:
                db.add_spin(message.from_user.id, value, points*20)
            case _:
                db.add_spin(message.from_user.id, value, 0)
        logger.info(f"{message.from_user.id} rolled {value}")

def is_allowed_topic(message: types.Message):
    return (
        message.chat.id == TARGET_CHAT_ID and
        message.message_thread_id == TARGET_TOPIC_ID
    )


@dp.message(Command("spin"))
async def cmd_spin(message: types.Message):
    if not is_allowed_topic(message):
        return

    val = await message.answer_dice(emoji="🎰")
    await asyncio.sleep(4)

    if message.from_user:
        db.add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)

        value = val.dice.value
        multiplier = SPECIAL_VALUES.get(value, 0)
        points = POINTS_BY_VALUE.get(value, 1) * multiplier

        db.add_spin(message.from_user.id, value, points)
        logger.info(f"{message.from_user.id} rolled {value} -> {points} points")


@dp.message(Command("Топ"))
@dp.message(Command("leaderboard"))
async def cmd_leaderboard(message: types.Message):
    if not is_allowed_topic(message):
        return

    data = db.get_leaderboard()
    text = "🏆 ТОП ИГРОКОВ\n\n" if data else "Нет данных."
    if data:
        for i, row in enumerate(data, 1):
            first_name, username, spins, points = row
            name = f"{username}" if username else first_name
            text += f"{i}. {name}\n   🎰 {spins} вращений\n   ⭐ {points} очков\n\n"

    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        message_thread_id=message.message_thread_id
    )


@dp.message(Command("mystats"))
async def cmd_mystats(message: types.Message):
    if not is_allowed_topic(message):
        return

    if not message.from_user:
        await message.bot.send_message(
            chat_id=message.chat.id,
            text="Не могу определить пользователя.",
            message_thread_id=message.message_thread_id
        )
        return

    stats = db.get_user_stats(message.from_user.id)
    if not stats:
        await message.bot.send_message(
            chat_id=message.chat.id,
            text="У вас нет вращений.",
            message_thread_id=message.message_thread_id
        )
        return

    text = "📊 ВАША СТАТИСТИКА\n\n"
    total_spins = 0
    total_points = 0
    for value, count, points in stats:
        total_spins += count
        total_points += points
        match value:
            case 22:
                text += f"🍇🍇🍇 → {count} раз ({points} очков)\n"
            case 1:
                text += f"🍾🍾🍾 → {count} раз ({points} очков)\n"
            case 43:
                text += f"🍋🍋🍋 → {count} раз ({points} очков)\n"
            case 64:
                text += f"7️⃣7️⃣7️⃣ → {count} раз ({points} очков)\n"

    text += f"\n🎰 Всего: {total_spins}\n⭐ Очков: {total_points}"

    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        message_thread_id=message.message_thread_id
    )


@dp.message(Command("topicid"))
async def cmd_topicid(message: types.Message):
    text = f"ID темы: {message.message_thread_id}" if message.message_thread_id else "Это не тема форума."
    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        message_thread_id=message.message_thread_id
    )


@dp.message(Command("chatid"))
async def cmd_chatid(message: types.Message):
    await message.bot.send_message(
        chat_id=message.chat.id,
        text=str(message.chat.id),
        message_thread_id=message.message_thread_id
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    if not is_allowed_topic(message):
        return

    help_text = (
        "📖 Доступные команды бота:\n\n"
        "/spin — крутить слот 🎰\n"
        "/Топ — показать топ игроков по очкам 🎰\n"
        "/leaderboard — показать топ игроков 🎰\n"
        "/mystats — показать вашу статистику вращений 🎰\n"
        "/topicid — показать ID текущей темы форума 🏷️\n"
        "/chatid — показать ID текущего чата 💬\n"
        "/help — показать это сообщение с командами ℹ️\n"
    )

    await message.bot.send_message(
        chat_id=message.chat.id,
        text=help_text,
        message_thread_id=message.message_thread_id
    )


async def start_bot(token: str):
    db.init_db()
    bot = Bot(token=token)

    logger.info("Бот запущен")
    await dp.start_polling(bot)
