from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: Optional[int] = None) -> Optional[int]:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    return int(val)


def _get_str(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    return val


@dataclass(frozen=True)
class Config:
    discord_token: str

    guild_id: Optional[int]
    staff_role_id: int
    member_role_id: Optional[int]

    welcome_channel_id: int
    log_channel_id: int
    transcript_channel_id: int
    status_channel_id: int

    tickets_category_id: Optional[int]

    brand_color_hex: str
    website_url: str

    ticket_cooldown_seconds: int
    ticket_close_action: str  # "lock" or "delete"
    ticket_auto_delete_seconds: int  # 0 disables auto-delete after closing (only applies when close_action="lock")

    presence_rotate_seconds: int

    # NEW: member counter channel rename
    member_count_channel_id: Optional[int]
    member_count_name_template: str  # uses {count}
    
    owner_role_id: int
    muted_role_id: Optional[int]


def load_config() -> Config:
    token = _get_str("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing in .env")

    staff_role_id = _get_int("STAFF_ROLE_ID")
    if not staff_role_id:
        raise RuntimeError("STAFF_ROLE_ID is missing in .env")
    
    owner_role_id = _get_int("OWNER_ROLE_ID")
    if not owner_role_id:
        raise RuntimeError("OWNER_ROLE_ID is missing in .env")

    welcome_channel_id = _get_int("WELCOME_CHANNEL_ID")
    log_channel_id = _get_int("LOG_CHANNEL_ID")
    transcript_channel_id = _get_int("TRANSCRIPT_CHANNEL_ID")
    status_channel_id = _get_int("STATUS_CHANNEL_ID")

    missing = []
    for k, v in [
        ("WELCOME_CHANNEL_ID", welcome_channel_id),
        ("LOG_CHANNEL_ID", log_channel_id),
        ("TRANSCRIPT_CHANNEL_ID", transcript_channel_id),
        ("STATUS_CHANNEL_ID", status_channel_id),
    ]:
        if not v:
            missing.append(k)
    if missing:
        raise RuntimeError(f"Missing channel IDs in .env: {', '.join(missing)}")

    close_action = (_get_str("TICKET_CLOSE_ACTION", "lock") or "lock").lower().strip()
    if close_action not in {"lock", "delete"}:
        raise RuntimeError("TICKET_CLOSE_ACTION must be 'lock' or 'delete'")

    auto_del = int(_get_str("TICKET_AUTO_DELETE_SECONDS", "0") or "0")
    if auto_del < 0:
        auto_del = 0

    template = _get_str("MEMBER_COUNT_NAME_TEMPLATE", "🥭 MEMBERS - {count}") or "🥭 MEMBERS - {count}"
    if "{count}" not in template:
        # Ensure it always has a placeholder
        template = template + " {count}"

    return Config(
        discord_token=token,

        guild_id=_get_int("GUILD_ID"),
        staff_role_id=staff_role_id,
        member_role_id=_get_int("MEMBER_ROLE_ID"),

        welcome_channel_id=welcome_channel_id,  # type: ignore[arg-type]
        log_channel_id=log_channel_id,  # type: ignore[arg-type]
        transcript_channel_id=transcript_channel_id,  # type: ignore[arg-type]
        status_channel_id=status_channel_id,  # type: ignore[arg-type]

        tickets_category_id=_get_int("TICKETS_CATEGORY_ID"),

        brand_color_hex=_get_str("BRAND_COLOR_HEX", "#F9A826") or "#F9A826",
        website_url=_get_str("WEBSITE_URL", "https://mangomods.store") or "https://mangomods.store",
        
        owner_role_id=owner_role_id,
        muted_role_id=_get_int("MUTED_ROLE_ID"),

        ticket_cooldown_seconds=int(_get_str("TICKET_COOLDOWN_SECONDS", "0") or "0"),
        ticket_close_action=close_action,
        ticket_auto_delete_seconds=auto_del,

        presence_rotate_seconds=int(_get_str("PRESENCE_ROTATE_SECONDS", "30") or "30"),

        # NEW
        member_count_channel_id=_get_int("MEMBER_COUNT_CHANNEL_ID"),
        member_count_name_template=template,
    )