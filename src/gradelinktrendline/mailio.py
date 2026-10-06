"""Read .eml files and mbox exports into RawMessage records."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

from gradelinktrendline.fields import normalize_space
from gradelinktrendline.models import RawMessage

_FROM_SEPARATOR = re.compile(br"(?m)^From .*?\n")


def html_to_text(html: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1>", " ", html)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</p>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</tr>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</t[dh]>", "\n", cleaned)
    cleaned = re.sub(r"(?i)<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned).replace("\r\n", "\n").replace("\r", "\n")
    lines = [normalize_space(line) for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line)


def _decode_part(part: EmailMessage) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _bodies(msg: EmailMessage) -> tuple[str, str]:
    plain: list[str] = []
    html: list[str] = []
    parts: list[EmailMessage]
    if msg.is_multipart():
        parts = [part for part in msg.walk() if not part.is_multipart()]
    else:
        parts = [msg]
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain":
            plain.append(_decode_part(part))
        elif ctype == "text/html":
            html.append(_decode_part(part))
    html_text = "\n".join(piece.strip() for piece in html if piece.strip())
    plain_text = "\n".join(piece.strip() for piece in plain if piece.strip())
    if plain_text:
        body = plain_text
    elif html_text:
        body = html_to_text(html_text)
    else:
        body = ""
    body = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    return body, html_text


def _header_date(msg: EmailMessage) -> datetime | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_eml_bytes(raw: bytes, source: str) -> RawMessage:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    body_text, body_html = _bodies(msg)
    header_id = msg.get("Message-ID")
    if header_id and header_id.strip():
        message_id = header_id.strip()
    else:
        message_id = "sha256:" + hashlib.sha256(raw).hexdigest()
    sender = str(msg.get("From") or "")
    subject = str(msg.get("Subject") or "")
    return RawMessage(
        message_id=message_id,
        source=source,
        sender=sender,
        subject=subject,
        message_date=_header_date(msg),
        body_text=body_text,
        body_html=body_html,
        body_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _split_mbox(data: bytes) -> list[bytes]:
    data = data.replace(b"\r\n", b"\n")
    parts = _FROM_SEPARATOR.split(data)
    messages: list[bytes] = []
    for part in parts:
        if not part.strip():
            continue
        lines = []
        for line in part.splitlines(keepends=True):
            if line.startswith(b">From "):
                line = line[1:]
            lines.append(line)
        messages.append(b"".join(lines))
    return messages


def load_messages(path: Path) -> list[RawMessage]:
    if path.is_dir():
        found: list[RawMessage] = []
        for child in sorted(path.rglob("*")):
            if not child.is_file():
                continue
            if child.suffix.lower() in {".eml", ".mbox"}:
                found.extend(load_messages(child))
        return found
    suffix = path.suffix.lower()
    if suffix == ".eml":
        return [parse_eml_bytes(path.read_bytes(), source=str(path))]
    if suffix == ".mbox":
        messages = []
        for index, blob in enumerate(_split_mbox(path.read_bytes())):
            messages.append(parse_eml_bytes(blob, source=f"{path}#{index}"))
        return messages
    raise ValueError(f"unsupported input (expected a .eml file, .mbox file, or directory): {path}")
