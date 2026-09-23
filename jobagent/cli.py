from __future__ import annotations

import argparse
import asyncio
import sys
import time
import webbrowser
from datetime import timezone

from telethon.errors import FloodWaitError, RPCError
from telethon.tl.types import Channel

from jobagent import db
from jobagent.apply import compose_cover
from jobagent.config import Settings, load_settings
from jobagent.display import (
    clear_screen,
    field,
    heading,
    print_job_card,
    print_notice,
    print_scan_line,
    print_scan_summary,
    print_status,
    rule,
    telegram_post_url,
    term_width,
)
from jobagent.export import export_sheets
from jobagent.extract import extract_from_message
from jobagent.matcher import score_text
from jobagent.parse import parse_post
from jobagent.telegram_client import connected_client, qr_login, reset_session, send_cv


def _posted_at(message) -> str | None:
    date = getattr(message, "date", None)
    if not date:
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
            print_notice("Not joined or not found: " + ", ".join(sorted(missing)))
        if not watched:
            raise SystemExit("None of the configured channels were found in this account.")

        print()
        print(rule())
        print()
        heading("Scanning channels")
        print()
        with db.connect() as conn:
            total_channels = len(watched)
            for index, (title, entity) in enumerate(watched, start=1):
                username = _channel_key(entity)
                print_scan_line(index, total_channels, title, username)
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
    print_scan_summary(inserted, matched)


def cmd_status() -> None:
    db.init_db()
    min_score = 1
    with db.connect() as conn:
        try:
            settings = load_settings()
            min_score = settings.min_score
            db.rescore_new_jobs(conn, settings.keywords, settings.location_keywords)
        except SystemExit:
            pass
        tallies = db.counts(conn)
        inbox = len(db.list_inbox(conn, min_score))
    print_status(tallies, inbox)


def cmd_export() -> None:
    db.init_db()
    try:
        settings = load_settings()
        _enrich_applied(settings)
    except SystemExit:
        pass
    xlsx_path = _refresh_applied_sheet()
    print()
    print_notice(f"Wrote {xlsx_path}")
    print_notice("Open it in LibreOffice Calc or Excel.")
    print()


def _refresh_applied_sheet() -> str:
    _csv_path, xlsx_path = export_sheets()
    return xlsx_path


def _save_to_applied_list(
    job_id: int,
    *,
    apply_method: str,
    parsed: dict,
    notes: str | None = None,
) -> str:
    with db.connect() as conn:
        db.record_application(
            conn,
            job_id,
            apply_method=apply_method,
            parsed=parsed,
            notes=notes,
        )
    return _refresh_applied_sheet()


def _enrich_applied(settings: Settings) -> None:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'applied'
            """
        ).fetchall()
        for job in rows:
            parsed = parse_post(
                job["text"] or "",
                db.loads(job["urls"]),
                source_channel=job["channel_username"],
                blocked_channels=settings.channels,
                fetch_apply_page=True,
            )
            db.record_application(
                conn,
                job["id"],
                apply_method=job["apply_method"] or "telegram",
                parsed=parsed,
                notes=job["notes"],
                apply_status=job["apply_status"] or "applied",
            )


def cmd_applications() -> None:
    db.init_db()
    try:
        settings = load_settings()
        _enrich_applied(settings)
    except SystemExit:
        pass
    with db.connect() as conn:
        rows = db.list_applications(conn)
    width = term_width()
    print()
    print(rule(width))
    heading("Applications")
    print(rule(width))
    if not rows:
        print_notice("None yet. In review: a + y, or add after a manual apply.")
        print()
        return
    for job in rows:
        print()
        field("Date", job["applied_at"], width)
        field("Status", job["apply_status"] or "applied", width, strong=True)
        field("CompanyName", job["company"], width, strong=True)
        field("Position", job["position"], width)
        field("Salary", job["salary"], width)
        field("Remote", job["remote"], width)
        field("Location", job["location"], width)
        contact = job["telegram_contact"]
        field("Telegram", f"@{contact}" if contact else None, width)
        field("Apply", job["apply_url"], width)
        field(
            "Post",
            telegram_post_url(
                job["channel_username"],
                job["message_id"],
                job["channel_id"],
            ),
            width,
        )
        print(rule(width))
    xlsx_path = _refresh_applied_sheet()
    print()
    print_notice(f"Spreadsheet: {xlsx_path}")
    print_notice("Open it in LibreOffice Calc or Excel.")
    print_notice("Mark rejected: python -m jobagent outcome")
    print()


def cmd_outcome() -> None:
    db.init_db()
    with db.connect() as conn:
        rows = db.list_applications(conn)
    if not rows:
        print_notice("No applications to update.")
        return
    print()
    for job in rows:
        print(
            f"  {job['id']:>4}  {job['apply_status'] or 'applied':10}  "
            f"{job['company'] or '—'}  /  {job['position'] or '—'}"
        )
    print()
    raw = input("  Application id: ").strip()
    try:
        job_id = int(raw)
    except ValueError:
        print_notice("Not a number.")
        return
    status = input("  Status [applied/rejected/interview]: ").strip().lower()
    if status not in {"applied", "rejected", "interview"}:
        print_notice("Use applied, rejected, or interview.")
        return
    with db.connect() as conn:
        db.set_apply_status(conn, job_id, status)
    xlsx_path = _refresh_applied_sheet()
    print_notice(f"Saved id {job_id} as {status}.")
    print_notice(f"Updated {xlsx_path}")


def _open_apply(url: str | None) -> None:
    if not url:
        print_notice("No application link on this post.")
        return
    print_notice("Opening " + url)
    webbrowser.open(url)


async def cmd_review(settings: Settings) -> None:
    db.init_db()
    with db.connect() as conn:
        db.rescore_new_jobs(conn, settings.keywords, settings.location_keywords)
        inbox = db.list_inbox(conn, settings.min_score)
    if not inbox:
        print_notice("Inbox is empty. Run scan, or lower min_score / add keywords.")
        return

    total = len(inbox)
    for index, job in enumerate(inbox, start=1):
        emails = db.loads(job["emails"])
        urls = db.loads(job["urls"])
        keywords = db.loads(job["matched_keywords"])
        parsed = parse_post(
            job["text"] or "",
            urls,
            source_channel=job["channel_username"],
            blocked_channels=settings.channels,
            fetch_apply_page=True,
        )
        apply_url = parsed["apply_url"]
        telegram_contact = parsed["telegram_contact"]
        cover = compose_cover(
            settings.intro_message,
            position=parsed["position"],
            company=parsed["company"],
        )
        show_full = False
        while True:
            clear_screen()
            print_job_card(
                index=index,
                total=total,
                score=int(job["score"] or 0),
                channel=job["channel_title"] or "",
                username=job["channel_username"],
                posted_at=job["posted_at"],
                keywords=keywords,
                company=parsed["company"],
                position=parsed["position"],
                description=parsed["description"],
                apply_url=apply_url,
                post_url=telegram_post_url(
                    job["channel_username"],
                    job["message_id"],
                    job["channel_id"],
                ),
                telegram_contact=telegram_contact,
                emails=emails,
                body=job["text"] or "",
                show_full=show_full,
            )
            choice = input("  > ").strip().lower()
            if choice in {"m", "more", "full"}:
                show_full = True
                continue
            if choice in {"q", "quit"}:
                print()
                print_notice("Stopped. Remaining posts stay in the inbox.")
                print_notice("Applied jobs: data/applied.xlsx")
                print()
                return
            if choice in {"s", "skip", "n"}:
                with db.connect() as conn:
                    db.set_status(conn, job["id"], "skipped")
                break
            if choice in {"o", "open"}:
                _open_apply(apply_url)
                input("  Press Enter to continue. ")
                continue
            if choice in {"add", "l", "link", "email", "manual"}:
                method = "manual"
                if not telegram_contact and emails and not apply_url:
                    method = "email"
                elif not telegram_contact and apply_url:
                    method = "link"
                xlsx_path = _save_to_applied_list(
                    job["id"],
                    apply_method=method,
                    parsed=parsed,
                    notes="added from review",
                )
                print_notice("Added to the applied list.")
                print_notice(xlsx_path)
                break
            if choice in {"a", "apply", "y"}:
                if not telegram_contact:
                    print_notice(
                        "No Telegram HR contact on this post. Use o to open the link, then add."
                    )
                    input("  Press Enter to continue. ")
                    continue
                print()
                print_notice(f"Will send {settings.cv_path.name} to @{telegram_contact}")
                print_notice(cover)
                confirm = input("  Send now? [y/N] ").strip().lower()
                if confirm != "y":
                    print_notice("Not sent.")
                    input("  Press Enter to continue. ")
                    continue
                try:
                    await send_cv(settings, telegram_contact, cover)
                except FileNotFoundError as exc:
                    print_notice(str(exc))
                    input("  Press Enter to continue. ")
                    continue
                except ValueError as exc:
                    print_notice(str(exc))
                    input("  Press Enter to continue. ")
                    continue
                except FloodWaitError as exc:
                    print_notice(
                        f"Telegram asked to wait {exc.seconds}s. Stopping sends."
                    )
                    with db.connect() as conn:
                        db.set_status(conn, job["id"], "failed", notes=str(exc))
                    return
                except RPCError as exc:
                    print_notice(f"Send failed: {exc}")
                    with db.connect() as conn:
                        db.set_status(conn, job["id"], "failed", notes=str(exc))
                    break
                xlsx_path = _save_to_applied_list(
                    job["id"],
                    apply_method="telegram",
                    parsed=parsed,
                    notes=f"@{telegram_contact}",
                )
                print_notice(f"Sent to @{telegram_contact}.")
                print_notice(f"Saved in {xlsx_path}")
                if settings.send_delay_seconds:
                    time.sleep(settings.send_delay_seconds)
                break
            print_notice("Unknown choice. Use a, o, add, s, m, or q.")
            input("  Press Enter to continue. ")
    print()
    print_notice("Done. Applied jobs are in data/applied.xlsx")
    print()


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
    sub.add_parser("export", help="Rewrite data/applied.xlsx for LibreOffice or Excel")
    sub.add_parser("applications", help="Show saved applications")
    sub.add_parser("outcome", help="Mark an application applied/rejected/interview")
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
    if args.command == "applications":
        cmd_applications()
        return
    if args.command == "outcome":
        cmd_outcome()
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
