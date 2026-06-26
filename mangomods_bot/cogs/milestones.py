from __future__ import annotations

import os
import random
from datetime import datetime, timezone

import discord
from discord.ext import commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed
from mangomods_bot.utils.log import log_action


def _human_count(guild: discord.Guild) -> int:
    return sum(1 for m in guild.members if not m.bot)


def _parse_milestones(raw: str) -> list[int]:
    out: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except Exception:
                pass
    return sorted(set(m for m in out if m > 0))


_FLAVOR_LINES = [
    "The community keeps growing — thank you for being part of it. 🥭",
    "Big W for MangoMods. More members, more wins.",
    "This one's for the whole squad. Let's keep it going. 🔥",
    "Another milestone, another reason to celebrate.",
    "We started from nothing. Look at us now.",
    "The support has been unreal. Thank you all. 🥭",
    "MangoMods doesn't stop. Neither do you.",
    "We built this together. That's what it's about.",
]


class Milestones(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store = JSONStore("/data/milestones.json", {"last_milestone": 0})

        self.channel_id   = int(os.getenv("MILESTONE_CHANNEL_ID",    "0") or "0")
        self.ping_role_id = int(os.getenv("MILESTONE_PING_ROLE_ID",  "0") or "0")
        self.milestones   = (
            _parse_milestones(os.getenv("MILESTONE_LIST", ""))
            or [50, 100, 250, 500, 1000, 2500, 5000]
        )

    # ── Next goal helper ──────────────────────────────────────────────────────

    def _next_goal(self, current: int) -> int | None:
        for m in self.milestones:
            if m > current:
                return m
        return None

    # ── Milestone post ────────────────────────────────────────────────────────

    async def _post_milestone(
        self, guild: discord.Guild, milestone: int, humans: int
    ) -> None:
        if not self.channel_id:
            return

        try:
            ch = guild.get_channel(self.channel_id) or await self.bot.fetch_channel(self.channel_id)
        except Exception:
            return

        if not isinstance(ch, discord.TextChannel):
            return

        next_goal = self._next_goal(milestone)

        emb = mango_embed(
            self.bot,
            color   = "premium",
            footer  = f"{milestone:,} Members Milestone",
        )

        # Author — guild name + icon
        if guild.icon:
            emb.set_author(name=guild.name, icon_url=guild.icon.url)
        else:
            emb.set_author(name=guild.name)

        emb.title = f"🎉  {milestone:,} Members!"
        emb.description = (
            f"{random.choice(_FLAVOR_LINES)}\n\n"
            f"We just hit **{milestone:,} members** in **{guild.name}**."
        )

        emb.add_field(
            name="👥  Current Count",
            value=f"**{humans:,}** humans",
            inline=True,
        )
        emb.add_field(
            name="🎯  Next Goal",
            value=f"**{next_goal:,}** members" if next_goal else "The sky 🌌",
            inline=True,
        )
        emb.add_field(
            name="🌐  Website",
            value=self.bot.config.website_url,
            inline=True,
        )

        # Thumbnail — guild icon
        if guild.icon:
            emb.set_thumbnail(url=guild.icon.url)

        # Banner — guild banner if available
        if guild.banner:
            emb.set_image(url=guild.banner.url)

        emb.timestamp = datetime.now(timezone.utc)

        # Ping role if configured
        content = ""
        if self.ping_role_id:
            role = guild.get_role(self.ping_role_id)
            if role:
                content = role.mention

        await ch.send(
            content=content or None,
            embed=emb,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

        await log_action(
            self.bot,
            "Milestone Celebrated",
            f"Guild: **{guild.name}**\nMilestone: **{milestone:,}**\nHumans: **{humans:,}**",
        )

    # ── Check and fire ────────────────────────────────────────────────────────

    async def check_milestones(self, guild: discord.Guild) -> None:
        if not guild.chunked:
            try:
                await guild.chunk()
            except Exception:
                pass

        humans    = _human_count(guild)
        eligible  = [m for m in self.milestones if m <= humans]
        if not eligible:
            return

        newest = max(eligible)
        data   = await self.store.read()
        last   = int(data.get("last_milestone", 0))

        if newest <= last:
            return

        # Write first — prevents double-fire on rapid joins
        data["last_milestone"] = newest
        await self.store.write(data)

        await self._post_milestone(guild, newest, humans)

    # ── Listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self.bot.config.guild_id:
            return
        guild = self.bot.get_guild(self.bot.config.guild_id)
        if guild:
            await self.check_milestones(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.check_milestones(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.check_milestones(member.guild)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Milestones(bot))
