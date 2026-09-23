from __future__ import annotations

import re
from urllib.parse import urlparse

from jobagent.apply import guess_telegram_contact
from jobagent.extract import URL_RE, extract_from_text
from jobagent.pages import fetch_apply_page as download_apply_page

APPLY_HOST_HIGH = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workable.com",
    "smartrecruiters.com",
    "breezy.hr",
    "hh.ru",
    "career.habr.com",
    "linkedin.com",
    "weworkremotely.com",
    "wantapply.com",
    "talanto.work",
    "up2staff.com",
    "python.org",
    "indeed.com",
    "djinni.co",
    "getmatch.ru",
    "habr.com",
    "docs.google.com",
    "forms.gle",
    "notion.site",
    "notion.so",
)
APPLY_HOST_MEDIUM = (
    "teletype.in",
    "telegra.ph",
)
SKIP_HOST = (
    "updatecv.me",
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "instagram.com",
)
NOISE_COMPANY = {
    "fintech",
    "it",
    "remote",
    "global",
    "fulltime",
    "itjob",
    "backend",
    "python",
    "developer",
    "russia",
    "ru",
}


def _clean_line(value: str) -> str:
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"[#|]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -:|")
    return value[:90]


def guess_company(text: str) -> str | None:
    if re.search(r"вакансии по python за неделю", text, re.IGNORECASE):
        return "Weekly digest (several jobs)"

    labeled = (
        r"(?im)^\s*(?:company\s*name|company|компания|employer)\s*[:\-–]\s*(.+)$"
    )
    match = re.search(labeled, text)
    if match:
        name = _clean_line(match.group(1).split("#")[0])
        if name:
            return name

    first = (text or "").splitlines()[0] if text else ""
    if "|" in first:
        last = _clean_line(first.split("|")[-1].split("#")[0])
        if last and last.lower() not in NOISE_COMPANY and len(last) >= 2:
            return last
    return None


def guess_position(text: str) -> str | None:
    labeled = (
        r"(?im)^\s*(?:title|position|role|должность|вакансия|позиция)\s*[:\-–]\s*(.+)$"
    )
    match = re.search(labeled, text or "")
    if match:
        name = _clean_line(match.group(1).split("#")[0])
        if name:
            return name

    first = (text or "").splitlines()[0] if text else ""
    first = re.sub(r"https?://\S+", "", first).strip()
    if "|" in first:
        name = _clean_line(first.split("|")[0])
        if name and len(name) >= 4:
            return name
    cleaned = _clean_line(first.split("#")[0])
    if cleaned and len(cleaned) >= 8 and not cleaned.lower().startswith("published"):
        return cleaned[:90]
    return None


_SKIP_DESC = re.compile(
    r"(?i)^(published time|company name|company|компания|title|position|role|"
    r"должность|вакансия|grades|location|anywhere|remote|forbidden locations|"
    r"tags|формат|связ|смотрите|смотреть)\b"
)


def short_description(text: str, limit: int = 420) -> str | None:
    labeled = re.search(
        r"(?is)(?:job description|описание|описание вакансии)\s*[:\-–]\s*(.+)",
        text or "",
    )
    blob = labeled.group(1) if labeled else (text or "")
    parts: list[str] = []
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("http"):
            continue
        if _SKIP_DESC.match(line):
            continue
        if line.startswith("👉") or "Job Description & Apply" in line:
            continue
        parts.append(re.sub(r"\s+", " ", line))
        if sum(len(item) for item in parts) >= limit:
            break
    if not parts:
        return None
    joined = " ".join(parts)
    if len(joined) > limit:
        return joined[: limit - 1].rsplit(" ", 1)[0] + "…"
    return joined


def _host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().lstrip("www.")
    except ValueError:
        return ""


def _url_rank(url: str, source_channel: str | None) -> int | None:
    host = _host(url)
    if any(host == skip or host.endswith("." + skip) for skip in SKIP_HOST):
        return None
    path = urlparse(url).path.lower()
    if source_channel and re.search(
        rf"(?:t\.me|telegram\.me)/{re.escape(source_channel)}(?:/|$)",
        url,
        re.IGNORECASE,
    ):
        return None
    if host in {"t.me", "telegram.me"}:
        return None
    if any(host == item or host.endswith("." + item) for item in APPLY_HOST_HIGH):
        return 3
    if "/jobs" in path or "/job/" in path or "apply" in path:
        return 3
    if any(host == item or host.endswith("." + item) for item in APPLY_HOST_MEDIUM):
        return 2
    if url.lower().startswith("http"):
        return 1
    return None


def _plain(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\\u003[cC]/?[a-zA-Z0-9]+\\u003[eE]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -:|,")
    return value


def guess_salary(text: str) -> str | None:
    labeled = re.search(
        r"(?im)^\s*(?:з/?п|зарплат[аые]|salary|compensation|pay)\s*[:\-–]\s*(.+)$",
        text or "",
    )
    raw = labeled.group(1) if labeled else None
    if not raw:
        inline = re.search(
            r"(?i)(?:з/?п|зарплат[аые]|salary)\s*[:\-–]?\s*"
            r"((?:от\s*|до\s*)?[\d\s.,]+(?:\s*[-–до]+\s*[\d\s.,]+)?\s*"
            r"(?:тыс(?:яч)?|k|\$|€|₽|usd|eur|руб(?:лей)?)[^\n,<]*)",
            text or "",
        )
        raw = inline.group(1) if inline else None
    if not raw:
        return None
    value = _plain(raw)
    clipped = re.search(
        r"(?i)(?:от\s+|до\s+|from\s+|up to\s+)?"
        r"[\d\s.,]+(?:\s*[-–до]+\s*[\d\s.,]+)?"
        r"\s*(?:тыс(?:яч)?\.?\s*)?"
        r"(?:руб(?:лей|\.)?|usd|eur|\$|€|₽|k)?"
        r"(?:\s+на руки)?"
        r"(?:\s*\([^)]{0,50}\))?",
        value,
    )
    if clipped:
        return clipped.group(0).strip(" -:|,")
    return value[:80]


def guess_remote(text: str) -> str | None:
    hay = text or ""
    if re.search(r"(?i)гибрид|hybrid", hay):
        return "hybrid"
    if re.search(r"(?i)удал[её]нн|remote\s*:\s*yes|\bremote\b|remote ru|remote global", hay):
        if re.search(r"(?i)office only|только офис|onsite only", hay):
            return "hybrid"
        return "yes"
    if re.search(r"(?i)\boffice\b|офис|onsite|on-site|на площад", hay):
        return "no"
    return None


def guess_location(text: str) -> str | None:
    labeled = re.search(
        r"(?im)^\s*(?:location|локация|локац[ия]|город|based)\s*[:\-–]\s*(.+)$",
        text or "",
    )
    if labeled:
        value = _clean_line(labeled.group(1).split("#")[0])
        if value:
            return value
    first = (text or "").splitlines()[0] if text else ""
    if "|" in first:
        parts = [p.strip() for p in first.split("|")]
        if len(parts) >= 2:
            mid = _clean_line(parts[1].split("#")[0])
            if mid and mid.lower() not in NOISE_COMPANY:
                return mid
    geo = re.search(
        r"(?i)\b(москва|russia|рф|remote ru|remote russia|remote global|"
        r"варшава|poland|польша|yerevan|ереван|armenia|казахстан|belarus|рб)\b",
        text or "",
    )
    if geo:
        return geo.group(1)
    return None


def pick_apply_url(
    urls: list[str],
    text: str,
    source_channel: str | None = None,
) -> str | None:
    found = list(urls)
    for extra in URL_RE.findall(text or ""):
        found.append(extra.rstrip(".,);"))
    ranked: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, url in enumerate(found):
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        rank = _url_rank(url, source_channel)
        if rank is None:
            continue
        ranked.append((rank, -index, url))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    return ranked[0][2]


def parse_post(
    text: str,
    urls: list[str] | None = None,
    source_channel: str | None = None,
    blocked_channels: list[str] | None = None,
    *,
    fetch_apply_page: bool = False,
) -> dict[str, str | None]:
    """Company, role, apply link, and Telegram HR contact. Does not send."""
    _contacts, emails, extracted_urls = extract_from_text(text or "")
    all_urls = list(urls or []) + extracted_urls
    apply_url = pick_apply_url(all_urls, text or "", source_channel)
    page = download_apply_page(apply_url) if fetch_apply_page and apply_url else None
    blob = "\n".join(part for part in [text or "", page or ""] if part)
    contact = guess_telegram_contact(
        blob,
        source_channel=source_channel,
        blocked=blocked_channels,
    )
    return {
        "company": guess_company(blob) or guess_company(text or ""),
        "position": guess_position(text or "") or guess_position(blob),
        "description": short_description(text or "") or short_description(blob),
        "apply_url": apply_url,
        "telegram_contact": contact,
        "email": emails[0] if emails else None,
        "salary": guess_salary(blob),
        "remote": guess_remote(blob),
        "location": guess_location(blob),
    }
