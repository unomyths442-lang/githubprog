import os
from telethon import TelegramClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(BASE_DIR, "telethon.session")

api_id = int(input("API ID: ").strip())
api_hash = input("API HASH: ").strip()
phone = input("Номер телефона (с +): ").strip()

client = TelegramClient(SESSION_FILE, api_id, api_hash)

async def main():
    await client.start(phone=phone)
    me = await client.get_me()
    print(f"Авторизован как {me.username or me.first_name}")
    print(f"Файл сохранён: {SESSION_FILE}")

with client:
    client.loop.run_until_complete(main())
