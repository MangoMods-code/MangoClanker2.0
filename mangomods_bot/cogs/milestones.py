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
        if not part:
            continue
        try:
            out.append(int(part))
        except Exception:
            pass
    return sorted(set([m for m in out if m > 0]))


class Milestones(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store = JSONStore("/data/milestones.json", {"last_milestone": 0})

        self.channel_id = int(os.getenv("MILESTONE_CHANNEL_ID", "0") or "0")
        self.ping_role_id = int(os.getenv("MILESTONE_PING_ROLE_ID", "0") or "0")
        self.milestones = _parse_milestones(os.getenv("MILESTONE_LIST", "")) or [50, 100, 250, 500, 1000]

    async def _post_milestone(self, guild: discord.Guild, milestone: int, humans: int) -> None:
        if not self.channel_id:
            return

        ch = guild.get_channel(self.channel_id)
        if ch is None:
            try:
                ch = await self.bot.fetch_channel(self.channel_id)
            except Exception:
                return

        if not isinstance(ch, discord.TextChannel):
            return

        # fun lines (swap/add your own)
        lines = [
            "We’re growing fast — welcome to MangoMods 🍋",
            "Big W for the community 🥭",
            "More members, more wins. Let’s go!",
            "Thanks for being here — we’re just getting started.",
        ]
        desc = (
            f"### 🎉 Milestone Reached!\n"
            f"We just hit **{milestone} members** (humans only).\n\n"
            f"**Current count:** {humans}\n"
            f"{random.choice(lines)}"
        )

        emb = mango_embed(self.bot, title="🥭 MangoMods Milestone!", description=desc)
        emb.add_field(name="Website", value=self.bot.config.website_url, inline=True)
        emb.add_field(name="Next Goal", value=str(self._next_goal(milestone) or "—"), inline=True)
        emb.set_footer(text="MangoMods • Thank you for the support!")
        emb.timestamp = datetime.now(timezone.utc)

        content = ""
        if self.ping_role_id:
            role = guild.get_role(self.ping_role_id)
            if role:
                content = role.mention

        await ch.send(content=content, embed=emb)

        await log_action(self.bot, "Milestone Celebrated", f"Guild: **{guild.name}**\nMilestone: **{milestone}**\nHumans: **{humans}**")

    def _next_goal(self, current: int) -> int | None:
        for m in self.milestones:
            if m > current:
                return m
        return None

    async def check_milestones(self, guild: discord.Guild) -> None:
        humans = _human_count(guild)
        eligible = [m for m in self.milestones if m <= humans]
        if not eligible:
            return

        newest = max(eligible)
        data = await self.store.read()
        last = int(data.get("last_milestone", 0))

        # only fire once per milestone
        if newest <= last:
            return

        # update first (prevents double-fire if two joins happen fast)
        data["last_milestone"] = newest
        await self.store.write(data)

        await self._post_milestone(guild, newest, humans)

    @commands.Cog.listener()
    async def on_ready(self):
        # Run once at startup (safe due to last_milestone)
        guild = self.bot.get_guild(self.bot.config.guild_id) if self.bot.config.guild_id else (self.bot.guilds[0] if self.bot.guilds else None)
        if guild:
            await self.check_milestones(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.check_milestones(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # optional: you can also celebrate only on join; but this keeps state accurate
        await self.check_milestones(member.guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(Milestones(bot))