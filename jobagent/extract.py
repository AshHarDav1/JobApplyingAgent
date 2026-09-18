from __future__ import annotations

import re

from telethon.tl.types import (
    MessageEntityEmail,
    MessageEntityMention,
    MessageEntityTextUrl,
    MessageEntityUrl,
)

USERNAME_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{4,32})")
TME_RE = re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]+)", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
SKIP_TME = {"joinchat", "addstickers", "share", "socks", "proxy", "s", "c"}


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def extract_from_text(text: str) -> tuple[list[str], list[str], list[str]]:
    contacts = [match.group(1) for match in USERNAME_RE.finditer(text)]
    for match in TME_RE.finditer(text):
        name = match.group(1)
        if name.lower() not in SKIP_TME and not name.startswith("+"):
            contacts.append(name)
    emails = EMAIL_RE.findall(text)
    urls = URL_RE.findall(text)
    return _unique(contacts), _unique(emails), _unique(urls)


def extract_from_message(message) -> tuple[list[str], list[str], list[str]]:
    text = message.message or ""
    contacts, emails, urls = extract_from_text(text)
    for entity in message.entities or []:
        start = entity.offset
        end = entity.offset + entity.length
        chunk = text[start:end]
        if isinstance(entity, MessageEntityMention):
            contacts.append(chunk.lstrip("@"))
        elif isinstance(entity, MessageEntityEmail):
            emails.append(chunk)
        elif isinstance(entity, MessageEntityUrl):
            urls.append(chunk)
            extra = extract_from_text(chunk)
            contacts.extend(extra[0])
        elif isinstance(entity, MessageEntityTextUrl) and entity.url:
            urls.append(entity.url)
            extra = extract_from_text(entity.url)
            contacts.extend(extra[0])
    return _unique(contacts), _unique(emails), _unique(urls)
