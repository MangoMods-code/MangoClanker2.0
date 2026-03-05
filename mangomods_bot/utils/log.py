from __future__ import annotations

import discord

from .embeds import mango_embed

async def log_action(bot, title: str, description: str) -> None:
    """
    Sends a branded log embed to LOG_CHANNEL_ID (if accessible).
    """
    try:
        channel_id = bot.config.log_channel_id
        ch = bot.get_channel(channel_id)
        if ch is None:
            ch = await bot.fetch_channel(channel_id)
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            return

        emb = mango_embed(bot, title=title, description=description)
        await ch.send(embed=emb)
    except Exception:
        # Never crash core flows because logging failed.
        return