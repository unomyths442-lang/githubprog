import json
import os
import sys
import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
ACTIVITY_FILE = os.path.join(BASE_DIR, "activity.json")
TRACKED_FILE = os.path.join(BASE_DIR, "tracked.json")

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

    now = datetime.now()

    tracked = load_json(TRACKED_FILE)
    tracked_user = tracked.get("username", "").lower()

    if tracked_user and user.username and user.username.lower() == tracked_user:
        config = load_json(CONFIG_FILE)
        target_group = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")
        tracked_last = tracked.get("last_active")
        if tracked_last:
            try:
                last = datetime.fromisoformat(tracked_last)
                diff = now - last
                if diff.total_seconds() > 30:
                    msg = (
                        f"@{user.username} — активен: {now.strftime('%d.%m.%Y %H:%M:%S')} "
                        f"(прошло {int(diff.total_seconds())}с)"
                    )
                    if target_group:
                        await context.bot.send_message(chat_id=int(target_group), text=msg)
                    else:
                        await update.message.reply_text(msg)
            except Exception:
                pass
        tracked["last_active"] = now.isoformat()
        save_json(TRACKED_FILE, tracked)
        return

    config = load_json(CONFIG_FILE)
    home_group = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")
    if home_group:
        home_group = int(home_group)

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

    if user_id in activity:
        try:
            last = datetime.fromisoformat(activity[user_id]["last_active"])
            diff = now - last
            if diff.total_seconds() > 30:
                lines = []
                days, rem = divmod(int(diff.total_seconds()), 86400)
                hours, rem = divmod(rem, 3600)
                minutes = rem // 60
                if days:
                    lines.append(f"{days}д")
                if hours:
                    lines.append(f"{hours}ч")
                lines.append(f"{minutes}мин")
                away = " ".join(lines)
                name = activity[user_id].get("username") or user.full_name
                await update.message.reply_text(
                    f"{name} — был в сети {away} назад ({last.strftime('%d.%m.%Y %H:%M:%S')})"
                )
        except Exception:
            pass

    activity[user_id] = {
        "username": user.full_name,
        "last_active": now.isoformat()
    }
    save_json(ACTIVITY_FILE, activity)


async def activity_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    chat = update.effective_chat
    config = load_json(CONFIG_FILE)
    home_group = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")
    if home_group:
        home_group = int(home_group)

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


async def setuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    if not context.args:
        await update.message.reply_text("Использование: /setuser <username> (без @)")
        return

    username = context.args[0].strip().lower().lstrip("@")
    tracked = {"username": username, "last_active": None}
    save_json(TRACKED_FILE, tracked)
    await update.message.reply_text(f"Отслеживается пользователь @{username}")


async def checklastactive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    tracked = load_json(TRACKED_FILE)
    username = tracked.get("username")
    last_active = tracked.get("last_active")
    if not username:
        await update.message.reply_text("Пользователь не задан. Используйте /setuser")
        return
    if not last_active:
        await update.message.reply_text(f"@{username} — активность не обнаружена")
        return
    try:
        dt = datetime.fromisoformat(last_active)
        diff = datetime.now() - dt
        sec = int(diff.total_seconds())
        await update.message.reply_text(
            f"@{username} — последняя активность: {dt.strftime('%d.%m.%Y %H:%M:%S')} "
            f"(прошло {sec}с)"
        )
    except Exception:
        await update.message.reply_text(f"@{username} — последняя активность: {last_active}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    chat = update.effective_chat

    if chat.type == "private":
        await update.message.reply_text("Бот работает только в группах. Добавьте его в группу.")
        return

    config = load_json(CONFIG_FILE)
    home_group = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")
    if home_group:
        home_group = int(home_group)

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
    app.add_handler(CommandHandler("setuser", setuser_command))
    app.add_handler(CommandHandler("checklastactive", checklastactive_command))
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
