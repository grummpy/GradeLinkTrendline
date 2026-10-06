import base64
import json
import urllib.parse
from pathlib import Path

import pytest

from gradelinktrendline.cli import main
from gradelinktrendline.gmail_fetch import (
    READONLY_SCOPE,
    GmailConfigError,
    _normalize_token,
    authorize_url,
    fetch_gmail,
    load_client,
)
from gradelinktrendline.privacy import disallowed_emails, scan_tree


def test_fixtures_reject_email_addresses_outside_example_com():
    problems = scan_tree(Path(__file__).parent / "fixtures")
    assert problems == []


def test_scanner_flags_other_domains(tmp_path: Path):
    sample = tmp_path / "note.txt"
    sample.write_text("write to teacher@school.edu please\n", encoding="utf-8")
    assert disallowed_emails(sample.read_text(encoding="utf-8")) == ["teacher@school.edu"]
    assert scan_tree(tmp_path) == [(str(sample), "teacher@school.edu")]


def test_scanner_allows_example_com(tmp_path: Path):
    sample = tmp_path / "note.txt"
    sample.write_text("Parent <parent@example.com>\n", encoding="utf-8")
    assert scan_tree(tmp_path) == []


def test_gitignore_covers_data_and_secrets():
    text = Path(".gitignore").read_text(encoding="utf-8")
    assert "/data/" in text
    assert "/secrets/" in text


def test_repo_has_no_stored_oauth_tokens():
    blocked = {"token.json", "gmail_token.json", "credentials.json"}
    found = []
    for path in Path(".").rglob("*"):
        if any(part in {".git", ".venv", "data", "secrets"} for part in path.parts):
            continue
        if path.name in blocked:
            found.append(str(path))
    assert found == []


def test_fetch_requires_a_client_file(tmp_path: Path):
    missing = tmp_path / "no-client.json"
    with pytest.raises(GmailConfigError):
        load_client(missing)
    code = main(
        [
            "fetch-gmail",
            "--client",
            str(missing),
            "--token",
            str(tmp_path / "secrets" / "gmail_token.json"),
            "--out",
            str(tmp_path / "gmail"),
        ]
    )
    assert code == 2
    assert not (tmp_path / "secrets" / "gmail_token.json").exists()


def test_authorize_url_is_readonly_only():
    url = authorize_url("client-id", "http://127.0.0.1:9/", "state-token")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["scope"] == [READONLY_SCOPE]
    assert "gmail.modify" not in url
    assert "gmail.compose" not in url
    assert "mail.google.com" not in url


def test_token_with_extra_scope_is_refused():
    with pytest.raises(GmailConfigError):
        _normalize_token(
            {
                "access_token": "ya29.test",
                "expires_in": 3600,
                "scope": READONLY_SCOPE + " https://www.googleapis.com/auth/gmail.modify",
            }
        )


def test_fetch_writes_eml_without_putting_the_token_in_the_message(tmp_path: Path, monkeypatch):
    client = tmp_path / "client.json"
    client.write_text(
        json.dumps({"installed": {"client_id": "id", "client_secret": "secret"}}),
        encoding="utf-8",
    )
    token_path = tmp_path / "secrets" / "gmail_token.json"
    out = tmp_path / "mail"
    monkeypatch.setattr(
        "gradelinktrendline.gmail_fetch.obtain_token",
        lambda _client, _path: {"access_token": "ya29.test", "scope": READONLY_SCOPE},
    )
    eml = (
        b"From: GradeLink Alerts <alerts@example.com>\n"
        b"Subject: Low grade alert\n"
        b"Message-ID: <fetched@example.com>\n"
        b"\n"
        b"Student: Student A\n"
    )
    encoded = base64.urlsafe_b64encode(eml).decode("ascii").rstrip("=")

    def fake_get(url: str, access_token: str) -> dict[str, object]:
        assert access_token == "ya29.test"
        if "format=raw" in url:
            return {"raw": encoded}
        return {"messages": [{"id": "abc123"}]}

    monkeypatch.setattr("gradelinktrendline.gmail_fetch.api_get", fake_get)
    count = fetch_gmail(client, token_path, out, query="from:alerts@example.com")
    assert count == 1
    saved = (out / "abc123.eml").read_bytes()
    assert saved == eml
    assert b"ya29.test" not in saved
    assert not token_path.exists()
