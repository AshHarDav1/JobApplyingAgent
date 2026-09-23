from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from jobagent.paths import DATA_DIR

FOLLOW_HOSTS = {"teletype.in", "telegra.ph"}
CACHE_PATH = DATA_DIR / "url_cache.json"
MAX_BYTES = 400_000
TIMEOUT = 8


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def can_follow(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower().lstrip("www.")
    return host in FOLLOW_HOSTS


def decode_page(raw: str) -> str:
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), raw)
    text = text.replace("\\/", "/")
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def fetch_apply_page(url: str) -> str | None:
    """Download a teletype/telegra job page. Cached under data/url_cache.json."""
    if not can_follow(url):
        return None
    cache = _load_cache()
    hit = cache.get(url)
    if isinstance(hit, dict) and hit.get("text"):
        return str(hit["text"])
    request = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (JobApplyingAgent; +local)"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read(MAX_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return None
    text = decode_page(raw)
    cache[url] = {"text": text[:20000]}
    _save_cache(cache)
    return cache[url]["text"]
