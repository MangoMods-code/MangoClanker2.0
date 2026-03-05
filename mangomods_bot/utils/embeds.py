from __future__ import annotations

import discord
from datetime import datetime, timezone

def brand_color(bot) -> discord.Colour:
    hx = getattr(getattr(bot, "config", None), "brand_color_hex", "#F9A826")
    hx = hx.replace("#", "").strip()
    try:
        return discord.Colour(int(hx, 16))
    except Exception:
        return discord.Colour.orange()

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def mango_embed(bot, title: str | None = None, description: str | None = None) -> discord.Embed:
    e = discord.Embed(
        title=title if title else None,
        description=description if description else None,
        colour=brand_color(bot),
        timestamp=now_utc(),
    )
    return e