from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional

import discord
from discord.ext import commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.log import log_action

import re

_DURATION_RE = re.compile(r"^\s*(\d+)\s*(s|m|h|d|w)\s*$", re.IGNORECASE)

def parse_duration(text: str) -> Optional[timedelta]:
    m = _DURATION_RE.match(text or "")
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    if n <= 0:
        return None
    if unit == "s":
        return timedelta(seconds=n)
    if unit == "m":
        return timedelta(minutes=n)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    if unit == "w":
        return timedelta(weeks=n)
    return None

MAX_TIMEOUT = timedelta(days=28)

class ReviewsGuard(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store = JSONStore("/data/reviews_guard.json", {"violations": {}})

        # env config (kept simple)
        self.reviews_channel_id = int(os.getenv("REVIEWS_CHANNEL_ID", "0") or "0")
        self.max_warnings = int(os.getenv("REVIEWS_MAX_WARNINGS", "3") or "3")
        self.timeout_text = os.getenv("REVIEWS_TIMEOUT_DURATION", "10m") or "10m"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.reviews_channel_id:
            return
        if message.channel.id != self.reviews_channel_id:
            return

        # ignore bots/webhooks (allow other bots to post announcements, etc.)
        if message.author.bot or message.webhook_id is not None:
            return

        # Only enforce in guild text channels
        if not message.guild or not isinstance(message.author, discord.Member):
            return

        # Try delete immediately
        try:
            await message.delete()
        except Exception:
            # if we can't delete, bail silently
            return

        uid = str(message.author.id)
        data = await self.store.read()
        data.setdefault("violations", {})
        data["violations"][uid] = int(data["violations"].get(uid, 0)) + 1
        count = int(data["violations"][uid])
        await self.store.write(data)

        # Warn user via DM (best) or fall back to reply in channel (won't work since we delete)
        warn_msg = (
            f"⚠️ Please don’t chat in **#{message.channel.name}** — it’s for automated vouches/announcements only.\n"
            f"Warnings: **{count}/{self.max_warnings}**"
        )
        try:
            await message.author.send(warn_msg)
        except Exception:
            pass

        await log_action(
            self.bot,
            "Reviews Channel Message Deleted",
            f"User: {message.author.mention} (`{message.author.id}`)\n"
            f"Channel: <#{self.reviews_channel_id}>\n"
            f"Warnings: **{count}/{self.max_warnings}**"
        )

        # Timeout after hitting max warnings
        if count >= self.max_warnings:
            td = parse_duration(self.timeout_text) or timedelta(minutes=10)
            if td > MAX_TIMEOUT:
                td = MAX_TIMEOUT

            # prevent re-timeout spam: reset counter after punishment
            data = await self.store.read()
            data.setdefault("violations", {})
            data["violations"][uid] = 0
            await self.store.write(data)

            try:
                await message.author.timeout(td, reason="Repeated messages in reviews channel")
            except Exception:
                return

            await log_action(
                self.bot,
                "Reviews Channel Timeout Applied",
                f"User: {message.author.mention} (`{message.author.id}`)\n"
                f"Duration: **{self.timeout_text}**\n"
                f"Reason: Repeated messages in reviews channel"
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(ReviewsGuard(bot))