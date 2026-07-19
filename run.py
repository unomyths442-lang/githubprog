import os
import sys
import json
import asyncio
import logging
from datetime import datetime

from telethon import TelegramClient
from telethon.tl.types import UserStatusOnline

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
    handlers=[logging.StreamHandler(sys.stdout)]
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

last_was_online = False

async def telethon_monitor(token, target_group, stop_event):
    global last_was_online

    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_file = os.path.join(BASE_DIR, "telethon.session")
    client = TelegramClient(session_file, api_id, api_hash)
    await client.start()

    while not stop_event.is_set():
        try:
            tracked = load_json(TRACKED_FILE)
            username = tracked.get("username", "")
            if not username or not target_group:
                await asyncio.sleep(30)
                continue

            entity = await client.get_entity(username)
            is_online = isinstance(entity.status, UserStatusOnline)
            now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

            if is_online and not last_was_online:
                import httpx
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                async with httpx.AsyncClient() as c:
                    await c.post(url, json={"chat_id": int(target_group), "text": f"@{username} зашёл в сеть: {now}"})
                logger.info(f"ONLINE: @{username}")

            if not is_online and last_was_online:
                import httpx
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                async with httpx.AsyncClient() as c:
                    await c.post(url, json={"chat_id": int(target_group), "text": f"@{username} вышел из сети: {now}"})
                logger.info(f"OFFLINE: @{username}")

            last_was_online = is_online

        except Exception as e:
            logger.error(f"Monitor: {e}")

        await asyncio.sleep(30)

async def track_activity(update, context):
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    user = update.effective_user
    now = datetime.now()

    tracked = load_json(TRACKED_FILE)
    tu = tracked.get("username", "").lower()
    if tu and user.username and user.username.lower() == tu:
        config = load_json(CONFIG_FILE)
        tg = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")
        tl = tracked.get("last_active")
        notify = False
        if tl:
            try:
                diff = now - datetime.fromisoformat(tl)
                if diff.total_seconds() > 30:
                    notify = True
            except:
                notify = True
        else:
            notify = True
        if notify:
            msg = f"@{user.username} — активен: {now.strftime('%d.%m.%Y %H:%M:%S')}"
            if tl:
                try:
                    diff = now - datetime.fromisoformat(tl)
                    msg += f" (прошло {int(diff.total_seconds())}с)"
                except:
                    pass
            if tg:
                await context.bot.send_message(chat_id=int(tg), text=msg)
            else:
                await update.message.reply_text(msg)
        tracked["last_active"] = now.isoformat()
        save_json(TRACKED_FILE, tracked)
        return

    config = load_json(CONFIG_FILE)
    hg = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")
    if hg:
        hg = int(hg)
    if hg is None:
        config["home_group_id"] = chat.id
        config["home_group_title"] = chat.title or "Группа"
        save_json(CONFIG_FILE, config)
        hg = chat.id
        logger.info(f"Группа сохранена: {chat.title}")
    if chat.id != hg:
        return

    activity = load_json(ACTIVITY_FILE)
    uid = str(user.id)
    if uid in activity:
        try:
            last = datetime.fromisoformat(activity[uid]["last_active"])
            diff = now - last
            if diff.total_seconds() > 30:
                d, r = divmod(int(diff.total_seconds()), 86400)
                h, r = divmod(r, 3600)
                m = r // 60
                away = " ".join(x for x in [f"{d}д" if d else "", f"{h}ч" if h else "", f"{m}мин"] if x)
                name = activity[uid].get("username") or user.full_name
                await update.message.reply_text(f"{name} — был в сети {away} назад ({last.strftime('%d.%m.%Y %H:%M:%S')})")
        except:
            pass
    activity[uid] = {"username": user.full_name, "last_active": now.isoformat()}
    save_json(ACTIVITY_FILE, activity)

async def activity_command(update, context):
    if not update.effective_chat:
        return
    chat = update.effective_chat
    config = load_json(CONFIG_FILE)
    hg = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")
    if hg:
        hg = int(hg)
    if chat.id != hg:
        return
    activity = load_json(ACTIVITY_FILE)
    if not activity:
        await update.message.reply_text("Пока нет данных об активности.")
        return
    sorted_u = sorted(activity.values(), key=lambda x: x["last_active"], reverse=True)[:10]
    lines = ["Активность в группе:"]
    for u in sorted_u:
        try:
            t = datetime.fromisoformat(u["last_active"]).strftime("%d.%m.%Y %H:%M:%S")
        except:
            t = u["last_active"]
        lines.append(f"• {u['username']} — {t}")
    await update.message.reply_text("\n".join(lines))

async def setuser_command(update, context):
    if not update.effective_chat:
        return
    if not context.args:
        await update.message.reply_text("Использование: /setuser <username> (без @)")
        return
    username = context.args[0].strip().lower().lstrip("@")
    save_json(TRACKED_FILE, {"username": username, "last_active": None})
    await update.message.reply_text(f"Отслеживается пользователь @{username}")

async def startactive_command(update, context):
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
        if sec > 30:
            await update.message.reply_text(f"@{username} — не активен (последний раз: {dt.strftime('%d.%m.%Y %H:%M:%S')}, прошло {sec}с)")
        else:
            await update.message.reply_text(f"@{username} — активен! Последний раз: {dt.strftime('%d.%m.%Y %H:%M:%S')}")
    except:
        await update.message.reply_text(f"@{username} — последняя активность: {last_active}")

async def start_command(update, context):
    if not update.effective_chat:
        return
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("Бот работает только в группах. Добавьте его в группу.")
        return
    config = load_json(CONFIG_FILE)
    hg = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")
    if hg:
        hg = int(hg)
    if hg is None:
        config["home_group_id"] = chat.id
        config["home_group_title"] = chat.title or "Группа"
        save_json(CONFIG_FILE, config)
        logger.info(f"Группа сохранена через /start: {chat.title}")
        await update.message.reply_text(f"Эта группа ({chat.title}) сохранена как основная. Теперь бот будет работать только здесь.")
    elif chat.id == hg:
        await update.message.reply_text("Бот уже настроен на эту группу.")
    else:
        await update.message.reply_text("Бот уже настроен на другую группу.")

async def main():
    token = os.environ.get("BOT_TOKEN", "8275919663:AAF66WbIgYXjsoOioGyaeDR5hRGMVRmoIk0")
    proxy = os.environ.get("PROXY")
    config = load_json(CONFIG_FILE)
    target_group = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")

    builder = Application.builder().token(token)
    if proxy:
        builder = builder.request(HTTPXRequest(proxy=proxy, connection_pool_size=1))
    app = builder.build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("setuser", setuser_command))
    app.add_handler(CommandHandler("startactive", startactive_command))
    app.add_handler(CommandHandler("activity", activity_command))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_activity))

    await app.initialize()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await app.start()

    has_telethon = os.environ.get("API_ID") and os.environ.get("API_HASH")
    if has_telethon:
        stop_event = asyncio.Event()
        asyncio.create_task(telethon_monitor(token, target_group, stop_event))
        logger.info("Мониторинг онлайн-статуса запущен")
    else:
        logger.info("Telethon не настроен. Работаю только по сообщениям.")

    logger.info("Бот запущен...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
