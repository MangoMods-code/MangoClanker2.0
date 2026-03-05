from __future__ import annotations

import re
from datetime import datetime, timezone

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def pretty_dt(dt_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return dt_iso

def sanitize_channel_name(text: str) -> str:
    """
    Discord channel names: lowercase, alnum, hyphens.
    """
    text = text.lower()
    text = text.replace(" ", "-")
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if not text:
        return "user"
    return text[:80]

def extract_user_id(raw: str) -> int | None:
    """
    Accepts a mention like <@123>, <@!123>, or a plain numeric ID.
    """
    digits = re.findall(r"\d{15,20}", raw)
    if not digits:
        return None
    try:
        return int(digits[0])
    except Exception:
        return None