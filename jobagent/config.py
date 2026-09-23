from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import dotenv_values

from jobagent.paths import CONFIG_PATH, ENV_PATH, ROOT


@dataclass
class Settings:
    api_id: int
    api_hash: str
    phone: str | None
    cv_path: Path
    keywords: list[str] = field(default_factory=list)
    location_keywords: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    min_score: int = 1
    scan_limit_per_channel: int = 80
    send_delay_seconds: int = 8
    intro_message: str = "Hello, I am interested in this position. Please find my CV attached."


def _norm_list(values: object) -> list[str]:
    if not values:
        return []
    if not isinstance(values, list):
        raise ValueError("Expected a YAML list")
    return [str(item).strip().lstrip("@").lower() for item in values if str(item).strip()]


def load_settings() -> Settings:
    env = {key: (value or "").strip() for key, value in dotenv_values(ENV_PATH).items()}
    api_id_raw = env.get("TELEGRAM_API_ID", "")
    api_hash = env.get("TELEGRAM_API_HASH", "")
    phone = env.get("TELEGRAM_PHONE") or None
    if phone:
        phone = phone.strip() or None

    if not api_id_raw or not api_hash:
        raise SystemExit(
            "Missing TELEGRAM_API_ID or TELEGRAM_API_HASH.\n"
            "Copy .env.example to .env and fill values from https://my.telegram.org"
        )
    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be a number.") from exc

    if not CONFIG_PATH.exists():
        raise SystemExit(f"Missing {CONFIG_PATH}. Copy config.example.yaml to config.yaml")

    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    cv_path = Path(raw.get("cv_path") or "data/AshotHarutyunyanCV.pdf")
    if not cv_path.is_absolute():
        cv_path = ROOT / cv_path

    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        phone=phone,
        cv_path=cv_path,
        keywords=_norm_list(raw.get("keywords")),
        location_keywords=_norm_list(raw.get("location_keywords")),
        channels=_norm_list(raw.get("channels")),
        min_score=int(raw.get("min_score") or 1),
        scan_limit_per_channel=int(raw.get("scan_limit_per_channel") or 80),
        send_delay_seconds=int(raw.get("send_delay_seconds") or 8),
        intro_message=str(
            raw.get("intro_message")
            or "Hello, I am interested in this position. Please find my CV attached."
        ).strip(),
    )
