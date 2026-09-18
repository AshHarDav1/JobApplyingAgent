from __future__ import annotations

from contextlib import asynccontextmanager
from getpass import getpass
from typing import AsyncIterator

from telethon import TelegramClient

from jobagent.config import Settings
from jobagent.paths import DATA_DIR, SESSION_PATH


def build_client(settings: Settings) -> TelegramClient:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return TelegramClient(str(SESSION_PATH), settings.api_id, settings.api_hash)


async def start_client(client: TelegramClient, settings: Settings) -> None:
    """Log in. Phone and codes are typed in this terminal only."""

    def phone() -> str:
        if settings.phone:
            return settings.phone
        return input("Phone number with country code (not stored in git): ").strip()

    await client.start(
        phone=phone,
        password=lambda: getpass("Two-factor password (hidden, empty if unused): "),
        code_callback=lambda: input("Login code from Telegram: ").strip(),
    )


@asynccontextmanager
async def connected_client(settings: Settings) -> AsyncIterator[TelegramClient]:
    client = build_client(settings)
    await start_client(client, settings)
    try:
        yield client
    finally:
        await client.disconnect()
