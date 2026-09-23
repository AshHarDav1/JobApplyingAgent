from __future__ import annotations

import os
import shutil
import sys
import textwrap
from datetime import datetime


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def term_width(default: int = 88) -> int:
    try:
        cols = shutil.get_terminal_size(fallback=(default, 24)).columns
    except OSError:
        cols = default
    return max(56, min(cols, 100))


def _sgr(*codes: str) -> str:
    if not color_enabled() or not codes:
        return ""
    return "\033[" + ";".join(codes) + "m"


RESET = "0"
DIM = "2"
BOLD = "1"
FG_MUTED = "38;5;245"
FG_TITLE = "38;5;252"
FG_ACCENT = "38;5;109"
FG_SCORE = "38;5;108"
FG_LABEL = "38;5;244"


def paint(text: str, *codes: str) -> str:
    if not codes or not color_enabled():
        return text
    return f"{_sgr(*codes)}{text}{_sgr(RESET)}"


def rule(width: int | None = None, char: str = "─") -> str:
    width = width or term_width()
    return paint(char * width, DIM, FG_MUTED)


def blank() -> None:
    print()


def clear_screen() -> None:
    if sys.stdout.isatty():
        print("\033[H\033[2J", end="")


def wrap_paragraphs(text: str, width: int) -> list[str]:
    lines: list[str] = []
    chunks = (text or "").replace("\r\n", "\n").split("\n")
    for chunk in chunks:
        stripped = chunk.strip()
        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        wrapped = textwrap.wrap(
            stripped,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        lines.extend(wrapped or [stripped])
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def format_posted(iso: str | None) -> str:
    if not iso:
        return "unknown date"
    try:
        stamp = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return stamp.strftime("%d %b %Y  %H:%M UTC")
    except ValueError:
        return iso


def telegram_post_url(
    username: str | None,
    message_id: int | None,
    channel_id: int | None = None,
) -> str | None:
    """Public t.me/channel/id link, or t.me/c/... when the channel has no username."""
    if not message_id:
        return None
    try:
        msg = int(message_id)
    except (TypeError, ValueError):
        return None
    handle = (username or "").strip().lstrip("@")
    if handle:
        return f"https://t.me/{handle}/{msg}"
    if channel_id is None or channel_id == "":
        return None
    try:
        raw = str(int(channel_id))
    except (TypeError, ValueError):
        return None
    if raw.startswith("-100"):
        raw = raw[4:]
    elif raw.startswith("-"):
        raw = raw[1:]
    if not raw:
        return None
    return f"https://t.me/c/{raw}/{msg}"


def field(label: str, value: str | None, width: int, *, strong: bool = False) -> None:
    label_text = f"  {label}:"
    col = 16
    pad = max(1, col - len(label_text))
    prefix = paint(label_text, DIM, FG_LABEL) + (" " * pad)
    rest_width = max(20, width - col)
    text = value.strip() if value else "—"
    wrapped = textwrap.wrap(text, width=rest_width) or ["—"]
    first = paint(wrapped[0], BOLD, FG_TITLE) if strong else paint(wrapped[0], FG_TITLE)
    print(prefix + first)
    indent = " " * col
    for extra in wrapped[1:]:
        print(indent + extra)


def print_job_card(
    *,
    index: int,
    total: int,
    score: int,
    channel: str,
    username: str | None,
    posted_at: str | None,
    keywords: list[str],
    company: str | None,
    position: str | None,
    description: str | None,
    apply_url: str | None,
    post_url: str | None,
    telegram_contact: str | None,
    emails: list[str],
    body: str,
    show_full: bool = False,
    body_limit: int = 12,
) -> bool:
    """Render one review card. Returns True if the body was truncated."""
    width = term_width()
    handle = f"@{username}" if username else ""
    desc_width = width - 16
    desc_lines = wrap_paragraphs(description or "", desc_width)
    body_lines = wrap_paragraphs(body, width - 4)
    truncated = False
    if not show_full:
        if len(desc_lines) > 6:
            desc_lines = desc_lines[:6]
            truncated = True
        if len(body_lines) > body_limit:
            truncated = True
    else:
        desc_lines = body_lines

    print()
    print(rule(width))
    print(
        paint(f"  Rank {index} / {total}", BOLD, FG_TITLE)
        + paint("    score ", DIM, FG_LABEL)
        + paint(str(score), BOLD, FG_SCORE)
    )
    print(rule(width))
    print()
    field("CompanyName", company, width, strong=True)
    field("Position", position, width, strong=True)
    field(
        "Telegram",
        f"@{telegram_contact}" if telegram_contact else None,
        width,
        strong=bool(telegram_contact),
    )
    field("Apply", apply_url, width)
    field("Post", post_url, width)
    print()
    print(paint("  Description:", DIM, FG_LABEL))
    if desc_lines:
        print()
        for line in desc_lines:
            print("    " + line)
        print()
    else:
        print("    " + paint("No description found", DIM, FG_MUTED))
        print()
    if truncated and not show_full:
        print("  " + paint("…  m  show more", DIM, FG_MUTED))
        print()
    print(rule(width))
    source = "  ".join(part for part in [channel, handle] if part)
    field("Source", source or "unknown", width)
    field("Posted", format_posted(posted_at), width)
    if keywords:
        field("Matched", ", ".join(keywords), width)
    if emails:
        field("Email", "  ".join(emails), width)
    print(rule(width))
    print()
    if telegram_contact:
        print(
            "  "
            + paint(f"a  send CV to @{telegram_contact}", BOLD, FG_SCORE)
            + paint("     o  open apply link", FG_TITLE)
        )
    else:
        print("  " + paint("o  open apply link     a  no Telegram HR contact", FG_TITLE))
    print(
        "  "
        + paint("add  add to applied list", BOLD, FG_SCORE if not telegram_contact else FG_TITLE)
        + paint("     s  skip     q  quit", FG_TITLE)
    )
    more = "     m  more description" if truncated else ""
    if more:
        print("  " + paint(more.strip(), DIM, FG_MUTED))
    print()
    return truncated


def heading(text: str) -> None:
    print("  " + paint(text, BOLD, FG_TITLE))


def print_scan_line(index: int, total: int, title: str, username: str | None) -> None:
    handle = f"@{username}" if username else ""
    print(
        paint(f"  {index:>2}/{total}  ", DIM, FG_MUTED)
        + paint(title, FG_TITLE)
        + (("  " + paint(handle, DIM, FG_ACCENT)) if handle else "")
    )


def print_scan_summary(inserted: int, matched: int) -> None:
    width = term_width()
    print()
    print(rule(width))
    print()
    print("  " + paint("Scan finished", BOLD, FG_TITLE))
    print()
    field("Stored", str(inserted), width)
    field("Matches", str(matched), width)
    print()
    print("  " + paint("Next  python -m jobagent review", DIM, FG_MUTED))
    print()
    print(rule(width))


def print_status(tallies: dict[str, int], inbox: int) -> None:
    width = term_width()
    print(rule(width))
    print()
    print("  " + paint("Job log", BOLD, FG_TITLE))
    print()
    if not tallies:
        print("  " + paint("Empty. Run scan first.", DIM, FG_MUTED))
        print()
        print(rule(width))
        return
    for status, count in sorted(tallies.items()):
        field(status, str(count), width)
    field("inbox", str(inbox), width)
    print()
    print(rule(width))


def print_notice(message: str) -> None:
    print("  " + paint(message, FG_ACCENT))
