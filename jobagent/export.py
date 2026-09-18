from __future__ import annotations

from openpyxl import Workbook

from jobagent import db
from jobagent.paths import CSV_PATH, DATA_DIR, XLSX_PATH

HEADERS = [
    "applied_at",
    "posted_at",
    "status",
    "apply_method",
    "score",
    "channel",
    "channel_username",
    "preview",
    "contacts",
    "emails",
    "urls",
    "notes",
]


def _preview(text: str | None, limit: int = 180) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"


def _row(job) -> list[str]:
    return [
        job["applied_at"] or "",
        job["posted_at"] or "",
        job["status"] or "",
        job["apply_method"] or "",
        str(job["score"] or 0),
        job["channel_title"] or "",
        job["channel_username"] or "",
        _preview(job["text"]),
        job["contacts"] or "",
        job["emails"] or "",
        job["urls"] or "",
        job["notes"] or "",
    ]


def export_sheets() -> tuple[str, str]:
    db.init_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with db.connect() as conn:
        rows = db.export_rows(conn)

    import csv

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADERS)
        for job in rows:
            writer.writerow(_row(job))

    book = Workbook()
    sheet = book.active
    sheet.title = "applications"
    sheet.append(HEADERS)
    for job in rows:
        sheet.append(_row(job))
    book.save(XLSX_PATH)
    return str(CSV_PATH), str(XLSX_PATH)
