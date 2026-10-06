"""Optional read-only Gmail fetch.

This module is not used by ingest, report, or serve. It runs only when you
invoke `glt fetch-gmail` and point it at your own OAuth client file.
Tokens are written to the path you pass (default: secrets/gmail_token.json),
which is gitignored. The requested scope is gmail.readonly and nothing else.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
DEFAULT_QUERY = "from:alerts@gradelink.com newer_than:365d"
DEFAULT_CLIENT = Path("secrets/gmail_client.json")
DEFAULT_TOKEN = Path("secrets/gmail_token.json")


class GmailConfigError(RuntimeError):
    pass


def load_client(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise GmailConfigError(
            f"No OAuth client file at {path}. Gmail fetch stays off until you pass "
            "your own client JSON. In Google Cloud, create an OAuth desktop client and "
            f"grant only {READONLY_SCOPE}."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    installed = data.get("installed") or data.get("web") or {}
    client_id = installed.get("client_id")
    client_secret = installed.get("client_secret")
    if not client_id or not client_secret:
        raise GmailConfigError("OAuth client file is missing client_id or client_secret.")
    token_uri = installed.get("token_uri") or TOKEN_URI
    return {"client_id": client_id, "client_secret": client_secret, "token_uri": token_uri}


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": READONLY_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{AUTH_URI}?{query}"


def fetch_gmail(
    client_path: Path,
    token_path: Path,
    out_dir: Path,
    query: str = DEFAULT_QUERY,
) -> int:
    client = load_client(client_path)
    token = obtain_token(client, token_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for message_id in list_message_ids(token["access_token"], query):
        raw = download_raw(token["access_token"], message_id)
        (out_dir / f"{message_id}.eml").write_bytes(raw)
        count += 1
    return count


def obtain_token(client: dict[str, str], token_path: Path) -> dict[str, object]:
    existing = _read_token(token_path)
    now = time.time()
    expires_at = float(existing.get("expires_at") or 0) if existing else 0
    if existing and existing.get("access_token") and expires_at > now + 60:
        return existing
    if existing and existing.get("refresh_token"):
        refreshed = refresh_access_token(client, str(existing["refresh_token"]))
        if existing.get("refresh_token") and not refreshed.get("refresh_token"):
            refreshed["refresh_token"] = existing["refresh_token"]
        _write_token(token_path, refreshed)
        return refreshed
    interactive = interactive_login(client)
    _write_token(token_path, interactive)
    return interactive


def refresh_access_token(client: dict[str, str], refresh_token: str) -> dict[str, object]:
    payload = _token_request(
        client,
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    return _normalize_token(payload)


def interactive_login(client: dict[str, str]) -> dict[str, object]:
    state = secrets.token_urlsafe(16)
    captured: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if params.get("state", [""])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch. Close this window and try again.")
                return
            code = params.get("code", [""])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing code.")
                return
            captured["code"] = code
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"GradeLink Trendline can use Gmail read-only. You can close this window.")

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/"
    url = authorize_url(client["client_id"], redirect_uri, state)
    print(f"Open this URL to authorize read-only Gmail access:\n{url}")
    webbrowser.open(url)
    server.handle_request()
    server.server_close()
    if "code" not in captured:
        raise GmailConfigError("Gmail authorization did not return a code.")
    payload = _token_request(
        client,
        {
            "grant_type": "authorization_code",
            "code": captured["code"],
            "redirect_uri": redirect_uri,
        },
    )
    return _normalize_token(payload)


def list_message_ids(access_token: str, query: str) -> list[str]:
    ids: list[str] = []
    page = ""
    while True:
        params = {"q": query, "maxResults": "100"}
        if page:
            params["pageToken"] = page
        url = f"{LIST_URL}?{urllib.parse.urlencode(params)}"
        payload = api_get(url, access_token)
        ids.extend(item["id"] for item in payload.get("messages", []))
        page = payload.get("nextPageToken") or ""
        if not page:
            return ids


def download_raw(access_token: str, message_id: str) -> bytes:
    url = f"{LIST_URL}/{urllib.parse.quote(message_id)}?format=raw"
    payload = api_get(url, access_token)
    raw = payload.get("raw")
    if not raw:
        raise GmailConfigError(f"Gmail did not return a raw message for {message_id}.")
    padded = raw + "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(padded)


def api_get(url: str, access_token: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GmailConfigError(f"Gmail API request failed ({exc.code}): {detail}") from exc


def _token_request(client: dict[str, str], fields: dict[str, str]) -> dict[str, object]:
    body = urllib.parse.urlencode(
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            **fields,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        client.get("token_uri") or TOKEN_URI,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GmailConfigError(f"Token request failed ({exc.code}): {detail}") from exc


def _normalize_token(payload: dict[str, object]) -> dict[str, object]:
    expires_in = float(payload.get("expires_in") or 3600)
    scope = str(payload.get("scope") or READONLY_SCOPE)
    if READONLY_SCOPE not in scope.split():
        raise GmailConfigError(f"Refusing a token whose scope is not {READONLY_SCOPE}.")
    extra = [item for item in scope.split() if item != READONLY_SCOPE]
    if extra:
        raise GmailConfigError(f"Refusing a token that includes extra scopes: {', '.join(extra)}.")
    return {
        "access_token": payload.get("access_token"),
        "refresh_token": payload.get("refresh_token"),
        "expires_at": time.time() + expires_in,
        "scope": READONLY_SCOPE,
    }


def _read_token(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_token(path: Path, token: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token), encoding="utf-8")
