from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from getpass import getpass
from typing import AsyncIterator

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import User

from jobagent.config import Settings
from jobagent.paths import DATA_DIR, SESSION_PATH


def session_files() -> list:
    return [
        path
        for path in SESSION_PATH.parent.glob(SESSION_PATH.name + ".session*")
        if path.is_file()
    ]


def reset_session() -> None:
    for path in session_files():
        path.unlink()
        print(f"Removed {path}")


def build_client(settings: Settings) -> TelegramClient:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return TelegramClient(str(SESSION_PATH), settings.api_id, settings.api_hash)


async def start_client(client: TelegramClient, settings: Settings) -> None:
    """Log in. Phone and codes are typed in this terminal only."""

    def phone() -> str:
        if settings.phone:
            return settings.phone
        return input("Phone number with country code (not stored in git): ").strip()

    def code() -> str:
        print(
            "\nTelegram will NOT SMS this code.\n"
            "Open the Telegram app → the official chat named Telegram.\n"
            "Use only the newest code. Old ones are already invalid.\n"
        )
        return input("Login code from the Telegram app: ").strip()

    await client.start(
        phone=phone,
        password=lambda: getpass("Two-factor password (hidden, empty if unused): "),
        code_callback=code,
    )


async def qr_login(client: TelegramClient) -> None:
    """Approve login by scanning a QR code in the official Telegram app."""
    await client.connect()
    if await client.is_user_authorized():
        return

    import qrcode

    print(
        "Scan this QR with the Telegram app:\n"
        "Settings → Devices → Link Desktop Device\n"
        "Keep this terminal open while you scan.\n"
    )
    qr = await client.qr_login()
    while True:
        image = qrcode.QRCode(border=1)
        image.add_data(qr.url)
        image.print_ascii(invert=True)
        try:
            await qr.wait()
            break
        except asyncio.TimeoutError:
            print("QR expired. New code below — scan again.")
            await qr.recreate()
        except SessionPasswordNeededError:
            await client.sign_in(password=getpass("Two-factor password: "))
            break


@asynccontextmanager
async def connected_client(settings: Settings) -> AsyncIterator[TelegramClient]:
    client = build_client(settings)
    await start_client(client, settings)
    try:
        yield client
    finally:
        await client.disconnect()


async def send_cv(settings: Settings, username: str, caption: str) -> None:
    """Send the local CV PDF to a Telegram user. Refuses channels/groups."""
    if not settings.cv_path.exists():
        raise FileNotFoundError(f"CV not found at {settings.cv_path}")
    async with connected_client(settings) as client:
        entity = await client.get_entity(username)
        if not isinstance(entity, User):
            raise ValueError(
                f"@{username} is a channel or group, not a person. Not sending."
            )
        await client.send_file(entity, str(settings.cv_path), caption=caption)
