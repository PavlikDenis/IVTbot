import logging
import os
import sqlite3
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

#НАСТРОЙКИ
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = -1002877541973
TARGET_TOPIC_ID = 56073
ADMINS = [5329886808]

DB_NAME = "casino_stats.db"
POINTS_BY_VALUE = {i: 1 for i in range(1, 65)}

#ЛОГИ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#БАЗА
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cur = conn.cursor()


def init_db():
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS spins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        dice_value INTEGER,
        points INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        emoji TEXT
    )
    """)
    conn.commit()

def is_allowed_topic(message: types.Message):
    return (
        message.chat.id == TARGET_CHAT_ID and
        message.message_thread_id == TARGET_TOPIC_ID
    )

#ФУНКЦИИ
def add_user(user: types.User):
    cur.execute("""
    INSERT INTO users(user_id, first_name, username)
    VALUES (?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        first_name=excluded.first_name,
        username=excluded.username,
        updated_at=CURRENT_TIMESTAMP
    """, (user.id, user.first_name, user.username))
    conn.commit()

def add_badge(user_id: int, emoji: str):
    cur.execute("""
    INSERT INTO user_badges(user_id, emoji)
    VALUES (?, ?)
    """, (user_id, emoji))
    conn.commit()


def get_user_badges(user_id: int):
    cur.execute("""
    SELECT emoji FROM user_badges
    WHERE user_id = ?
    """, (user_id,))

    rows = cur.fetchall()
    return [row[0] for row in rows]

def add_spin(user_id: int, value: int, points: int):
    cur.execute("""
    INSERT INTO spins(user_id, dice_value, points)
    VALUES (?, ?, ?)
    """, (user_id, value, points))
    conn.commit()


def get_leaderboard(limit=10):
    cur.execute("""
    SELECT users.first_name, users.username,
           COUNT(spins.id),
           SUM(spins.points)
    FROM spins
    JOIN users ON users.user_id = spins.user_id
    GROUP BY spins.user_id
    ORDER BY SUM(spins.points) DESC
    LIMIT ?
    """, (limit,))
    return cur.fetchall()


def get_user_stats(user_id):
    cur.execute("""
    SELECT dice_value, COUNT(*), SUM(points)
    FROM spins
    WHERE user_id = ?
    GROUP BY dice_value
    """, (user_id,))
    return cur.fetchall()


#ОБРАБОТЧИКИ
async def handle_dice(message: types.Message):
    # Проверяем чат и топик
    if message.chat.id != TARGET_CHAT_ID:
        return
    if message.message_thread_id != TARGET_TOPIC_ID:
        return
    if not message.dice or message.dice.emoji != "🎰":
        return
    if message.forward_date or message.forward_from or message.forward_sender_name:
        return

    value = message.dice.value
    points = POINTS_BY_VALUE.get(value, 1)

    if message.from_user:  # безопасная проверка
        add_user(message.from_user)
        if (value == 22):
            add_spin(message.from_user.id, value, points*5)
        elif (value == 1):
            add_spin(message.from_user.id, value, points*10)
        elif (value == 43):
            add_spin(message.from_user.id, value, points*5)
        elif (value == 64):
            add_spin(message.from_user.id, value, points*20)
        else:
            add_spin(message.from_user.id, value, 0)
        logger.info(f"{message.from_user.id} rolled {value}")


#КОМАНДЫ
async def cmd_leaderboard(message: types.Message):
    if not is_allowed_topic(message):
        return
    data = get_leaderboard()
    text = "🏆 ТОП ИГРОКОВ\n\n" if data else "Нет данных."
    if data:
        for i, row in enumerate(data, 1):
            if (i > 10):
                break
            first_name, username, spins, points = row
            name = f"{username}" if username else first_name
            text += f"{i}. {name}\n   🎰 {spins} вращений\n   ⭐ {points} очков\n\n"

    # используем bot.send_message напрямую с топиком
    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        message_thread_id=message.message_thread_id  # если None, отправится в основной чат
    )


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

    stats = get_user_stats(message.from_user.id)
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
    badges = get_user_badges(message.from_user.id)
    if badges:
        text += "🎖 Награды: " + " ".join(badges) + "\n\n"
    for value, count, points in stats:
        total_spins += count
        total_points += points
        if (value == 22):
            text += f"🍇🍇🍇 → {count} раз ({points} очков)\n"
        elif (value == 1):
            text += f"🍾🍾🍾 → {count} раз ({points} очков)\n"
        elif (value == 43):
            text += f"🍋🍋🍋 → {count} раз ({points} очков)\n"
        elif (value == 64):
            text += f"7️⃣7️⃣7️⃣ → {count} раз ({points} очков)\n"

    text += f"\n🎰 Всего: {total_spins}\n⭐ Очков: {total_points}"


    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        message_thread_id=message.message_thread_id
    )


async def cmd_topicid(message: types.Message):
    text = f"ID темы: {message.message_thread_id}" if message.message_thread_id else "Это не тема форума."
    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        message_thread_id=message.message_thread_id
    )


async def cmd_chatid(message: types.Message):
    await message.bot.send_message(
        chat_id=message.chat.id,
        text=str(message.chat.id),
        message_thread_id=message.message_thread_id
    )

# ======== КОМАНДА /help ========
async def cmd_help(message: types.Message):
    if not is_allowed_topic(message):
        return
    help_text = (
        "📖 Доступные команды бота:\n\n"
        "/Топ — показать топ игроков по очкам 🎰\n"
        "/mystats — показать вашу статистику вращений 🎰\n"
        "/topicid — показать ID текущей темы форума 🏷️\n"
        "/chatid — показать ID текущего чата 💬\n"
        "/help — показать это сообщение с командами ℹ️\n"
        "/creators — показывает разработчиков бота\n"
    )

    await message.bot.send_message(
        chat_id=message.chat.id,
        text=help_text,
        message_thread_id=message.message_thread_id  # отвечает прямо в теме
    )

async def creator_help(message: types.Message):
    if not is_allowed_topic(message):
        return
    creator_text = (
        "📖 Создатели:\n\n"
        "Андрей ℹ️\n"
        "Денис\n"
    )

    await message.bot.send_message(
        chat_id=message.chat.id,
        text=creator_text,
        message_thread_id=message.message_thread_id  # отвечает прямо в теме
    )

async def cmd_givebadge(message: types.Message):
    if message.from_user.id not in ADMINS:
        return

    args = message.text.split()

    if len(args) < 3:
        await message.reply("Правильно: /givebadge user_id emoji")
        return

    user_id = int(args[1])
    emoji = args[2]

    add_badge(user_id, emoji)

    await message.reply("Эмодзи выдано")

async def debug_all(message: types.Message):
    logger.info(f"DEBUG: chat_id={message.chat.id}, "
                f"topic_id={message.message_thread_id}, "
                f"type={message.dice.emoji if message.dice else 'not dice'}")


# ========= ЗАПУСК =========
async def main():
    init_db()
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # --- РЕГИСТРАЦИЯ КОМАНД ---
    dp.message.register(cmd_leaderboard, Command(commands=["Топ"]))
    dp.message.register(cmd_leaderboard, Command(commands=["top"]))
    dp.message.register(cmd_leaderboard, Command(commands=["топ"]))
    dp.message.register(cmd_leaderboard, Command(commands=["Top"]))
    dp.message.register(cmd_leaderboard, Command(commands=["leaderboard"]))
    dp.message.register(cmd_mystats, Command(commands=["mystats"]))
    dp.message.register(cmd_mystats, Command(commands=["stats"]))
    dp.message.register(cmd_topicid, Command(commands=["topicid"]))
    dp.message.register(cmd_chatid, Command(commands=["chatid"]))
    dp.message.register(cmd_help, Command(commands=["help"]))
    dp.message.register(creator_help, Command(commands=["creators"]))
    dp.message.register(cmd_givebadge, Command(commands=["givebage"]))

    # --- РЕГИСТРАЦИЯ ВСЕХ СООБЩЕНИЙ ---
    dp.message.register(handle_dice)
    dp.message.register(debug_all)

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())