import json
import os
import sys
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
ACTIVITY_FILE = os.path.join(BASE_DIR, "activity.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return

    config = load_json(CONFIG_FILE)
    home_group = config.get("home_group_id")

    if home_group is None:
        config["home_group_id"] = chat.id
        config["home_group_title"] = chat.title or "Группа"
        save_json(CONFIG_FILE, config)
        home_group = chat.id
        logger.info(f"Группа сохранена: {chat.title} (id: {chat.id})")

    if chat.id != home_group:
        return

    activity = load_json(ACTIVITY_FILE)
    user_id = str(user.id)
    activity[user_id] = {
        "username": user.full_name,
        "last_active": datetime.now().isoformat()
    }
    save_json(ACTIVITY_FILE, activity)


async def activity_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    chat = update.effective_chat
    config = load_json(CONFIG_FILE)
    home_group = config.get("home_group_id")

    if chat.id != home_group:
        return

    activity = load_json(ACTIVITY_FILE)
    if not activity:
        await update.message.reply_text("Пока нет данных об активности.")
        return

    sorted_users = sorted(
        activity.values(),
        key=lambda x: x["last_active"],
        reverse=True
    )

    lines = ["Активность в группе:"]
    for u in sorted_users[:10]:
        try:
            dt = datetime.fromisoformat(u["last_active"])
            time_str = dt.strftime("%d.%m.%Y %H:%M:%S")
        except Exception:
            time_str = u["last_active"]
        lines.append(f"• {u['username']} — {time_str}")

    await update.message.reply_text("\n".join(lines))


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    chat = update.effective_chat

    if chat.type == "private":
        await update.message.reply_text("Бот работает только в группах. Добавьте его в группу.")
        return

    config = load_json(CONFIG_FILE)
    home_group = config.get("home_group_id")

    if home_group is None:
        config["home_group_id"] = chat.id
        config["home_group_title"] = chat.title or "Группа"
        save_json(CONFIG_FILE, config)
        logger.info(f"Группа сохранена через /start: {chat.title} (id: {chat.id})")
        await update.message.reply_text(
            f"Эта группа ({chat.title}) сохранена как основная. "
            "Теперь бот будет работать только здесь."
        )
    elif chat.id == home_group:
        await update.message.reply_text(
            "Бот уже настроен на эту группу. Используйте /activity для просмотра активности."
        )
    else:
        await update.message.reply_text(
            "Бот уже настроен на другую группу и не может работать в нескольких группах."
        )


def main():
    token = os.environ.get("BOT_TOKEN", "8275919663:AAF66WbIgYXjsoOioGyaeDR5hRGMVRmoIk0")
    proxy = os.environ.get("PROXY")

    builder = Application.builder().token(token)
    if proxy:
        request = HTTPXRequest(proxy=proxy, connection_pool_size=1)
        builder = builder.request(request)
    app = builder.build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("activity", activity_command))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_activity))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        sys.exit(1)
