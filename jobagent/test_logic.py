from jobagent.extract import extract_from_text
from jobagent.matcher import score_text


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
