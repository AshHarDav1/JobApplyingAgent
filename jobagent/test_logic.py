from jobagent.display import wrap_paragraphs
from jobagent.extract import extract_from_text
from jobagent.matcher import score_text
from jobagent.parse import guess_company, guess_position, parse_post, pick_apply_url, short_description


def test_extract_contacts_and_email() -> None:
    contacts, emails, urls = extract_from_text(
        "Apply via @hr_team or https://t.me/hr_team and jobs@acme.com https://forms.gle/x"
    )
    assert "hr_team" in contacts
    assert "jobs@acme.com" in emails
    assert any("forms.gle" in url for url in urls)


def test_keyword_score() -> None:
    score, matched = score_text(
        "Hiring a Python backend developer, remote",
        ["python", "backend"],
        ["remote"],
    )
    assert score >= 5
    assert "python" in matched
    assert "remote" in matched


def test_middle_ranks_above_senior() -> None:
    keywords = ["python", "backend"]
    loc = ["remote"]
    middle, m_hits = score_text(
        "Middle Python backend developer, remote", keywords, loc
    )
    senior, s_hits = score_text(
        "Senior Python backend developer, remote", keywords, loc
    )
    mixed, mix_hits = score_text(
        "Middle+/Senior Python backend, remote", keywords, loc
    )
    assert "middle" in m_hits
    assert "senior" in s_hits
    assert "middle" in mix_hits
    assert middle > senior
    assert mixed > senior


def test_telegram_post_url() -> None:
    from jobagent.display import telegram_post_url

    assert telegram_post_url("Remoteit", 12345) == "https://t.me/Remoteit/12345"
    assert telegram_post_url("@remoteit", "88") == "https://t.me/remoteit/88"
    assert telegram_post_url(None, 10, -1001234567890) == "https://t.me/c/1234567890/10"
    assert telegram_post_url("", 10, 1234567890) == "https://t.me/c/1234567890/10"
    assert telegram_post_url(None, None, 1) is None


def test_wrap_keeps_paragraphs() -> None:
    lines = wrap_paragraphs("hello world\n\nsecond line is here", 12)
    assert "hello world" in lines
    assert "" in lines
    assert any(line.startswith("second") for line in lines)


def test_company_and_apply_link() -> None:
    remote_python = """Published time: 2026-09-15
Company name: Proxify AB
Title: Senior Backend Developer (Python)
https://weworkremotely.com/remote-jobs/proxify-ab-senior-backend-developer-python-10
"""
    parsed = parse_post(remote_python, source_channel="remote_python_jobs")
    assert parsed["company"] == "Proxify AB"
    assert parsed["position"] == "Senior Backend Developer (Python)"
    assert parsed["apply_url"] and "weworkremotely.com" in parsed["apply_url"]

    remoteit = (
        "BACKEND DEVELOPER (PYTHON) | REMOTE RUSSIA | FIRST VDS "
        "#remote #python https://teletype.in/@remoteit/D1IlIjdcCew"
    )
    parsed = parse_post(remoteit, source_channel="remoteit")
    assert parsed["company"] == "FIRST VDS"
    assert parsed["position"] == "BACKEND DEVELOPER (PYTHON)"
    assert parsed["apply_url"] and "teletype.in" in parsed["apply_url"]

    rabota = "Компания: i-Line\nhttps://t.me/pythonrabota/2321\nhttps://talanto.work/jobs/abc"
    assert guess_company(rabota) == "i-Line"
    assert "talanto.work" in (pick_apply_url([], rabota, "pythonrabota") or "")
    assert guess_position("Title: Python Developer\nCompany name: X") == "Python Developer"
    desc = short_description(
        "Company name: X\nTitle: Y\nJob description: Build APIs in Python and ship them."
    )
    assert desc and "Build APIs" in desc
    from jobagent.parse import guess_remote, guess_salary

    assert guess_remote("BACKEND | REMOTE RU | ACME") == "yes"
    assert guess_salary("з/п: от 300 тыс. рублей на руки")


def test_applied_sheet_row() -> None:
    from jobagent.export import HEADERS, sheet_row

    row = sheet_row(
        {
            "applied_at": "2026-09-18T16:06:41Z",
            "apply_status": "applied",
            "apply_method": "manual",
            "company": "Acme",
            "position": "Backend",
            "salary": "300k",
            "remote": "yes",
            "location": "REMOTE RU",
            "telegram_contact": "hrperson",
            "apply_url": "https://example.com/job",
            "channel_title": "Remote IT",
            "channel_username": "remoteit",
            "message_id": 13900,
            "channel_id": 1,
            "notes": "added from review",
        }
    )
    assert HEADERS[0] == "Date"
    assert row[0].startswith("18 Sep 2026")
    assert row[2] == "Acme"
    assert row[7] == "@hrperson"
    assert row[9] == "https://t.me/remoteit/13900"
    assert row[11] == "manual"


def test_telegram_hr_contact_not_channel() -> None:
    from jobagent.apply import compose_cover, guess_telegram_contact

    text = (
        "Backend Developer Python | i-Line\n"
        "Связаться с HR — @AlkeiAmanzholov"
    )
    assert (
        guess_telegram_contact(text, source_channel="pythonrabota")
        == "AlkeiAmanzholov"
    )
    assert guess_telegram_contact(
        "Apply in comments @pythonrabota",
        source_channel="pythonrabota",
        blocked=["pythonrabota"],
    ) is None
    assert (
        guess_telegram_contact(
            "Open interview @shortcut_py_bot",
            source_channel="pythonrabota",
        )
        is None
    )
    parsed = parse_post(text, source_channel="pythonrabota", blocked_channels=["pythonrabota"])
    assert parsed["telegram_contact"] == "AlkeiAmanzholov"
    cover = compose_cover(
        "Hi, I'm interested in the {position} role at {company}. Please find my CV attached.",
        position="Backend Developer Python",
        company="i-Line",
    )
    assert "Backend Developer Python" in cover
    assert "i-Line" in cover


def test_contact_from_teletype_contact_heading() -> None:
    from jobagent.apply import guess_telegram_contact
    from jobagent.pages import decode_page

    raw = (
        r'<h2>CONTACT</h2><h2><a href="https:\u002F\u002Ft.me\u002Fviharycoach">'
        r"https://t.me/viharycoach</a></h2> @remoteit"
    )
    page = decode_page(raw)
    assert (
        guess_telegram_contact(page, source_channel="remoteit", blocked=["remoteit"])
        == "viharycoach"
    )
