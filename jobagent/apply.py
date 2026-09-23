from __future__ import annotations

import re

from jobagent.extract import SKIP_TME, TME_RE, USERNAME_RE

HR_CONTACT_RE = re.compile(
    r"(?i)(?:связ(?:аться|йтесь)?\s+с\s+hr|писать|пишите|резюме(?:\s+на)?|"
    r"отправ(?:ить|ляйте)?\s+резюме|contact|apply|hr)\s*[-—:]*\s*@([A-Za-z0-9_]{4,32})"
)
TME_HR_RE = re.compile(
    r"(?is)(?:связ(?:аться|йтесь)?\s+с\s+hr|писать|пишите|резюме|contact|контакт|hr)"
    r".{0,400}?(?:https?://)?t\.me/([A-Za-z0-9_]{4,32})"
)


def _blocked(source_channel: str | None, extra: list[str] | None) -> set[str]:
    names = {item.lower().lstrip("@") for item in (extra or [])}
    if source_channel:
        names.add(source_channel.lower().lstrip("@"))
    names.update(SKIP_TME)
    return names


def _ok(name: str, deny: set[str], *, allow_bot: bool) -> bool:
    key = name.lower().lstrip("@")
    if not key or key in deny:
        return False
    if key.endswith("bot") and not allow_bot:
        return False
    return True


def guess_telegram_contact(
    text: str,
    *,
    source_channel: str | None = None,
    blocked: list[str] | None = None,
) -> str | None:
    """Return an HR/person username, never the job channel itself."""
    deny = _blocked(source_channel, blocked)
    blob = text or ""

    match = HR_CONTACT_RE.search(blob)
    if match and _ok(match.group(1), deny, allow_bot=True):
        return match.group(1)

    match = TME_HR_RE.search(blob)
    if match and _ok(match.group(1), deny, allow_bot=True):
        return match.group(1)

    for match in TME_RE.finditer(blob):
        if _ok(match.group(1), deny, allow_bot=False):
            return match.group(1)

    for match in USERNAME_RE.finditer(blob):
        if _ok(match.group(1), deny, allow_bot=False):
            return match.group(1)
    return None


def compose_cover(
    template: str,
    *,
    position: str | None,
    company: str | None,
) -> str:
    position = (position or "this role").strip()
    company = (company or "your team").strip()
    fallback = (
        f"Hi, I'm interested in the {position} role at {company}. "
        "Please find my CV attached."
    )
    try:
        text = (template or "").format(position=position, company=company).strip()
    except (KeyError, ValueError, IndexError):
        text = fallback
    return (text or fallback)[:1000]
