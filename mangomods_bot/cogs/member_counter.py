from __future__ import annotations

import asyncio
import discord
from discord.ext import commands

from mangomods_bot.utils.log import log_action


class MemberCounter(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._lock = asyncio.Lock()

    async def _ensure_chunked(self, guild: discord.Guild) -> None:
        """
        Ensures member cache is populated (helps accuracy after restarts).
        Safe to call repeatedly.
        """
        try:
            if not guild.chunked:
                await guild.chunk()
        except Exception:
            pass

    async def update_counter(self, guild: discord.Guild) -> None:
        channel_id = getattr(self.bot.config, "member_count_channel_id", None)
        if not channel_id:
            return

        template = getattr(self.bot.config, "member_count_name_template", "🥭 MEMBERS - {count}") or "🥭 MEMBERS - {count}"

        async with self._lock:
            await self._ensure_chunked(guild)

            # Humans only
            humans = sum(1 for m in guild.members if not m.bot)
            new_name = template.replace("{count}", str(humans)).strip()
            if not new_name:
                return

            ch = guild.get_channel(channel_id)
            if ch is None:
                try:
                    fetched = await self.bot.fetch_channel(channel_id)
                    ch = fetched
                except Exception:
                    return

            # Your channel looks like a voice channel, but support a few types
            if not isinstance(ch, (discord.VoiceChannel, discord.StageChannel, discord.TextChannel)):
                return

            if ch.name == new_name:
                return

            try:
                await ch.edit(name=new_name, reason="MangoMods human member count update")
                await log_action(self.bot, "Member Count Updated", f"Set `{new_name}` in **{guild.name}**")
            except Exception:
                return

    @commands.Cog.listener()
    async def on_ready(self):
        # Update on startup
        guild = self.bot.get_guild(self.bot.config.guild_id) if self.bot.config.guild_id else (self.bot.guilds[0] if self.bot.guilds else None)
        if guild:
            await self.update_counter(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.update_counter(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self.update_counter(member.guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(MemberCounter(bot))