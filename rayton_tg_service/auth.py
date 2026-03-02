"""
One-time authorization script for the Rayton Telethon service.

Run ONCE on the server to create the session file:
    python auth.py

After successful auth, a .session file is created.
The main service (main.py) uses this file and will NOT ask for credentials again.

Requirements:
    TG_API_ID, TG_API_HASH must be set in .env or environment.
    TG_SESSION (optional) — session file name, default: rayton_service
"""

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_PATH = os.environ.get("TG_SESSION", "rayton_service")


async def main():
    print(f"Authorizing Telethon session: {SESSION_PATH!r}")
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Already authorized as: {me.first_name} ({me.phone})")
        await client.disconnect()
        return

    phone = input("Enter phone number (with country code, e.g. +380501234567): ").strip()
    await client.send_code_request(phone)

    code = input("Enter the code you received in Telegram: ").strip()
    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        # 2FA is enabled
        password = input("Enter your 2FA password: ").strip()
        await client.sign_in(password=password)

    me = await client.get_me()
    print(f"\nSuccess! Authorized as: {me.first_name} (id={me.id})")
    print(f"Session saved to: {SESSION_PATH}.session")
    print("\nYou can now start the service with:")
    print("    uvicorn main:app --host 0.0.0.0 --port 8001")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
