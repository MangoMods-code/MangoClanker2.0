from __future__ import annotations

import os
from datetime import datetime, timezone

import discord

# ── Context-aware color palette ───────────────────────────────────────────────
# Call context_color("success") instead of hardcoding 0x57F287 everywhere.

COLORS: dict[str, int] = {
    "brand":    0xF9A826,  # mango gold   — default, info, neutral
    "success":  0x57F287,  # green        — join, verify complete, undetected
    "error":    0xED4245,  # red          — ban, detected, failure
    "warning":  0xF9A826,  # gold         — warn, risk, caution
    "info":     0x5865F2,  # blurple      — userinfo, cases, stats
    "muted":    0x95A5A6,  # grey         — testing, muted, inactive
    "premium":  0xFFD700,  # bright gold  — milestones, giveaways
}


def context_color(context: str = "brand") -> discord.Colour:
    return discord.Colour(COLORS.get(context, COLORS["brand"]))


def brand_color(bot=None) -> discord.Colour:
    """
    Legacy helper — kept so existing cogs that call brand_color(bot) don't break.
    Reads BRAND_COLOR_HEX from env; falls back to mango gold.
    """
    hx = os.getenv("BRAND_COLOR_HEX", "F9A826").replace("#", "").strip()
    try:
        return discord.Colour(int(hx, 16))
    except Exception:
        return discord.Colour(COLORS["brand"])


def _logo_url() -> str | None:
    """
    Set BRAND_LOGO_URL in .env to a direct image URL (png/jpg/gif).
    Used as the footer icon and set_author icon on key embeds.
    Leave blank to omit — no broken image icons.
    """
    return os.getenv("BRAND_LOGO_URL", "").strip() or None


def _footer_text(suffix: str = "") -> str:
    name = os.getenv("BRAND_NAME", "MangoMods").strip()
    return f"{name}  •  {suffix}" if suffix else name


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Core embed builder ────────────────────────────────────────────────────────

def mango_embed(
    bot=None,
    *,
    title: str | None = None,
    description: str | None = None,
    color: str | int | discord.Colour | None = None,
    footer: str = "",
    thumbnail: str | None = None,
    author_name: str | None = None,
    author_icon: str | None = None,
    timestamp: bool = True,
) -> discord.Embed:
    """
    Central embed factory. Every embed in the bot should come through here.

    Parameters
    ----------
    bot         : commands.Bot instance (used for brand color fallback).
    title       : Embed title.
    description : Embed description.
    color       : A context string ("success", "error", "warning", "info", "muted",
                  "premium", "brand"), a raw hex int, or a discord.Colour.
                  Defaults to brand gold.
    footer      : Suffix appended after the brand name in the footer.
                  e.g. footer="Step 1 of 2" → "MangoMods  •  Step 1 of 2"
    thumbnail   : URL for the embed thumbnail (top-right image).
    author_name : If set, adds a set_author line with the brand logo icon.
    author_icon : Override for the author icon URL (defaults to BRAND_LOGO_URL).
    timestamp   : Whether to attach the current UTC timestamp (default True).
    """

    # Resolve colour
    if color is None:
        resolved = brand_color(bot)
    elif isinstance(color, str):
        resolved = context_color(color)
    elif isinstance(color, int):
        resolved = discord.Colour(color)
    else:
        resolved = color

    emb = discord.Embed(
        title       = title or None,
        description = description or None,
        colour      = resolved,
        timestamp   = now_utc() if timestamp else None,
    )

    # Footer — always brand-stamped
    logo = _logo_url()
    footer_str = _footer_text(footer)
    emb.set_footer(
        text     = footer_str,
        icon_url = logo or None,
    )

    # Optional thumbnail
    if thumbnail:
        emb.set_thumbnail(url=thumbnail)

    # Optional author line
    if author_name:
        emb.set_author(
            name     = author_name,
            icon_url = (author_icon or logo) or None,
        )

    return emb


# ── Convenience builders ──────────────────────────────────────────────────────

def success_embed(bot=None, title: str = "✅  Done", description: str = "", **kwargs) -> discord.Embed:
    return mango_embed(bot, title=title, description=description, color="success", **kwargs)


def error_embed(bot=None, title: str = "❌  Error", description: str = "", **kwargs) -> discord.Embed:
    return mango_embed(bot, title=title, description=description, color="error", **kwargs)


def warning_embed(bot=None, title: str = "⚠️  Warning", description: str = "", **kwargs) -> discord.Embed:
    return mango_embed(bot, title=title, description=description, color="warning", **kwargs)


def info_embed(bot=None, title: str = "ℹ️  Info", description: str = "", **kwargs) -> discord.Embed:
    return mango_embed(bot, title=title, description=description, color="info", **kwargs)
