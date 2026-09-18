from __future__ import annotations

import argparse
import asyncio
import sys
import time
import webbrowser
from datetime import datetime, timezone

from telethon.errors import FloodWaitError, RPCError
from telethon.tl.types import Channel

from jobagent import db
from jobagent.config import Settings, load_settings
from jobagent.export import export_sheets
from jobagent.extract import extract_from_message
from jobagent.matcher import score_text
from jobagent.telegram_client import connected_client, qr_login, reset_session


def _posted_at(message) -> str | None:
    date = getattr(message, "date", None)
    if not date:
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _preview(text: str, limit: int = 400) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"


def _channel_key(entity) -> str | None:
    username = getattr(entity, "username", None)
    return username.lower() if username else None


async def cmd_login(settings: Settings, *, use_qr: bool = False) -> None:
    if use_qr:
        from jobagent.telegram_client import build_client

        client = build_client(settings)
        try:
            await qr_login(client)
            me = await client.get_me()
        finally:
            await client.disconnect()
    else:
        async with connected_client(settings) as client:
            me = await client.get_me()
    name = " ".join(part for part in [me.first_name, me.last_name] if part)
    print(f"Logged in as {name} (id {me.id}). Session saved under data/.")


async def cmd_channels(settings: Settings) -> None:
    async with connected_client(settings) as client:
        print("Joined channels / supergroups:\n")
        found = 0
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not isinstance(entity, Channel):
                continue
            username = getattr(entity, "username", None) or ""
            kind = "channel" if getattr(entity, "broadcast", False) else "group"
            label = f"@{username}" if username else f"id:{entity.id}"
            print(f"  {label:28}  {kind:8}  {dialog.name}")
            found += 1
        print(f"\n{found} listed. Copy usernames (without @) into config.yaml -> channels")


async def _watched_entities(client, settings: Settings):
    wanted = set(settings.channels)
    watched = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not isinstance(entity, Channel):
            continue
        key = _channel_key(entity)
        if key and key in wanted:
            watched.append((dialog.name, entity))
    return watched


async def cmd_scan(settings: Settings) -> None:
    if not settings.channels:
        raise SystemExit(
            "config.yaml has an empty channels list.\n"
            "Run: python -m jobagent channels\n"
            "Then paste usernames into config.yaml (no @)."
        )
    db.init_db()
    inserted = 0
    matched = 0
    async with connected_client(settings) as client:
        watched = await _watched_entities(client, settings)
        missing = set(settings.channels) - {
            (_channel_key(entity) or "") for _, entity in watched
        }
        missing.discard("")
        if missing:
            print("Not joined or not found:", ", ".join(sorted(missing)))
        if not watched:
            raise SystemExit("None of the configured channels were found in this account.")

        with db.connect() as conn:
            for title, entity in watched:
                username = _channel_key(entity)
                print(f"Scanning {title} (@{username})...")
                async for message in client.iter_messages(
                    entity, limit=settings.scan_limit_per_channel
                ):
                    text = message.message or ""
                    if not text.strip():
                        continue
                    contacts, emails, urls = extract_from_message(message)
                    score, hits = score_text(
                        text, settings.keywords, settings.location_keywords
                    )
                    payload = {
                        "channel_id": entity.id,
                        "channel_title": title,
                        "channel_username": username,
                        "message_id": message.id,
                        "posted_at": _posted_at(message),
                        "text": text,
                        "urls": db.dumps(urls),
                        "contacts": db.dumps(contacts),
                        "emails": db.dumps(emails),
                        "score": score,
                        "matched_keywords": db.dumps(hits),
                        "created_at": db.utc_now(),
                    }
                    if db.upsert_job(conn, payload):
                        inserted += 1
                        if score >= settings.min_score:
                            matched += 1
    print(f"New posts stored: {inserted}. New keyword matches: {matched}.")
    print("Next: python -m jobagent review")


def cmd_status() -> None:
    db.init_db()
    min_score = 1
    try:
        min_score = load_settings().min_score
    except SystemExit:
        pass
    with db.connect() as conn:
        tallies = db.counts(conn)
        inbox = len(db.list_inbox(conn, min_score))
    print("Job log:")
    if not tallies:
        print("  (empty — run scan first)")
        return
    for status, count in sorted(tallies.items()):
        print(f"  {status:16} {count}")
    print(f"  inbox (to review) {inbox}")


def cmd_export() -> None:
    csv_path, xlsx_path = export_sheets()
    print(f"Wrote {csv_path}")
    print(f"Wrote {xlsx_path}")


async def _send_cv(client, settings: Settings, username: str) -> None:
    if not settings.cv_path.exists():
        raise SystemExit(f"CV not found at {settings.cv_path}. Put a PDF there.")
    entity = await client.get_entity(username)
    await client.send_file(entity, str(settings.cv_path), caption=settings.intro_message)


def _open_first_url(urls: list[str]) -> None:
    if not urls:
        print("No links on this post.")
        return
    print(f"Opening {urls[0]}")
    webbrowser.open(urls[0])


async def cmd_review(settings: Settings) -> None:
    db.init_db()
    with db.connect() as conn:
        inbox = db.list_inbox(conn, settings.min_score)
    if not inbox:
        print("Inbox is empty. Run scan, or lower min_score / add keywords.")
        return

    sent = 0
    async with connected_client(settings) as client:
        total = len(inbox)
        for index, job in enumerate(inbox, start=1):
            contacts = db.loads(job["contacts"])
            emails = db.loads(job["emails"])
            urls = db.loads(job["urls"])
            keywords = db.loads(job["matched_keywords"])
            print("\n" + "=" * 72)
            print(
                f"[{index}/{total}] score {job['score']}  "
                f"@{job['channel_username'] or '?'}  {job['posted_at'] or ''}"
            )
            if keywords:
                print("matched:", ", ".join(keywords))
            if contacts:
                print("telegram:", ", ".join("@" + c for c in contacts))
            if emails:
                print("email:", ", ".join(emails))
            if urls:
                print("links:", " ".join(urls[:3]))
            print(_preview(job["text"] or ""))

            while True:
                print(
                    "\n[a] apply via Telegram   [l] mark applied after link/email\n"
                    "[o] open first link      [s] skip   [q] quit"
                )
                choice = input("> ").strip().lower()
                if choice in {"q", "quit"}:
                    print("Done. python -m jobagent export  writes the spreadsheet.")
                    return
                if choice in {"s", "skip", "n"}:
                    with db.connect() as conn:
                        db.set_status(conn, job["id"], "skipped")
                    break
                if choice in {"o", "open"}:
                    _open_first_url(urls)
                    continue
                if choice in {"l", "link", "email"}:
                    submitted = input("Did you submit it? [y/N] ").strip().lower() == "y"
                    if emails and not urls:
                        method, pending = "email", "pending_email"
                    else:
                        method, pending = "link", "pending_link"
                    with db.connect() as conn:
                        db.set_status(
                            conn,
                            job["id"],
                            "applied" if submitted else pending,
                            apply_method=method,
                        )
                    break
                if choice not in {"a", "apply", "y"}:
                    print("Unknown choice.")
                    continue
                if not contacts:
                    print("No Telegram contact on this post. Use [l] or [o] instead.")
                    continue
                target = contacts[0]
                confirm = input(
                    f"Send CV to @{target} from your account? [y/N] "
                ).strip().lower()
                if confirm != "y":
                    print("Not sent.")
                    continue
                try:
                    await _send_cv(client, settings, target)
                except FloodWaitError as exc:
                    print(f"Telegram asked to wait {exc.seconds}s. Stopping sends.")
                    with db.connect() as conn:
                        db.set_status(conn, job["id"], "failed", notes=str(exc))
                    return
                except RPCError as exc:
                    print(f"Send failed: {exc}")
                    with db.connect() as conn:
                        db.set_status(conn, job["id"], "failed", notes=str(exc))
                    break
                with db.connect() as conn:
                    db.set_status(
                        conn,
                        job["id"],
                        "applied",
                        apply_method="telegram",
                        notes=f"@{target}",
                    )
                sent += 1
                print(f"Sent. Logged as applied at {datetime.now().strftime('%Y-%m-%d')}.")
                if sent and settings.send_delay_seconds:
                    time.sleep(settings.send_delay_seconds)
                break
    print("Done. python -m jobagent export  writes the spreadsheet.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m jobagent",
        description="Scan joined Telegram job channels from your personal account.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    login = sub.add_parser("login", help="Log in once and save a local session file")
    login.add_argument(
        "--qr",
        action="store_true",
        help="Scan a QR code in the Telegram app (no SMS / login code)",
    )
    login.add_argument(
        "--reset",
        action="store_true",
        help="Delete the local session and start login from scratch",
    )
    sub.add_parser("channels", help="List channels this account already joined")
    sub.add_parser("scan", help="Fetch new posts from config.yaml channels")
    sub.add_parser("review", help="Apply / skip matches in the terminal")
    sub.add_parser("export", help="Write CSV and Excel of applied jobs")
    sub.add_parser("status", help="Show counts in the local log")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        cmd_status()
        return
    if args.command == "export":
        cmd_export()
        return
    settings = load_settings()
    if args.command == "login":
        if args.reset:
            reset_session()
        asyncio.run(cmd_login(settings, use_qr=args.qr))
        return
    if args.command == "channels":
        asyncio.run(cmd_channels(settings))
        return
    if args.command == "scan":
        asyncio.run(cmd_scan(settings))
        return
    if args.command == "review":
        asyncio.run(cmd_review(settings))
        return
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
