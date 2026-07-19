import os
import sys
import json
import asyncio
import logging
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.types import UserStatusOnline, UserStatusOffline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(BASE_DIR, "telethon.session")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TRACKED_FILE = os.path.join(BASE_DIR, "tracked.json")
TRACKED_USERNAME = ""

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


last_status = {}


async def send_telegram_message(token, chat_id, text):
    import httpx
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": int(chat_id), "text": text})


async def monitor_user(client, token, target_group):
    global last_status
    last_user = None
    last_was_online = False

    while True:
        try:
            tracked = load_json(TRACKED_FILE)
            username = tracked.get("username", "")
            if not username or not target_group:
                await asyncio.sleep(30)
                continue

            if not last_user:
                last_user = username
                last_was_online = False

            entity = await client.get_entity(username)
            status = entity.status

            is_online = isinstance(status, UserStatusOnline)
            now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

            prev = last_status.get(username)
            last_status[username] = is_online

            if is_online and not last_was_online:
                msg = f"@{username} — зашёл в сеть: {now_str}"
                await send_telegram_message(token, target_group, msg)
                logger.info(f"ONLINE: @{username} at {now_str}")

            if prev is not None and not is_online and prev:
                msg = f"@{username} — вышел из сети: {now_str}"
                await send_telegram_message(token, target_group, msg)
                logger.info(f"OFFLINE: @{username} at {now_str}")

            last_was_online = is_online
            last_user = username

        except Exception as e:
            logger.error(f"Monitor error: {e}")

        await asyncio.sleep(30)


async def main():
    token = os.environ.get("BOT_TOKEN", "8275919663:AAF66WbIgYXjsoOioGyaeDR5hRGMVRmoIk0")
    config = load_json(CONFIG_FILE)
    target_group = config.get("home_group_id") or os.environ.get("HOME_GROUP_ID")

    api_id_env = os.environ.get("API_ID")
    api_hash_env = os.environ.get("API_HASH")

    if api_id_env and api_hash_env:
        api_id = int(api_id_env)
        api_hash = api_hash_env
    else:
        api_id = int(input("Введите API ID (my.telegram.org): ").strip())
        api_hash = input("Введите API HASH (my.telegram.org): ").strip()
        os.environ["API_ID"] = str(api_id)
        os.environ["API_HASH"] = api_hash

    client = TelegramClient(SESSION_FILE, api_id, api_hash)

    await client.start()
    logger.info("Telethon client connected")

    if not target_group:
        logger.error("HOME_GROUP_ID не указан!")
        return

    logger.info(f"Мониторинг запущен. Целевая группа: {target_group}")

    await monitor_user(client, token, target_group)


if __name__ == "__main__":
    asyncio.run(main())
