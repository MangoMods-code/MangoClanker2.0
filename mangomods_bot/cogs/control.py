from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.utils.log import log_action
from pyfiglet import figlet_format


class Control(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _is_owner(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.owner_role_id for r in member.roles)

    @app_commands.command(name="shutdownbot", description="Shut down the bot (owner only).")
    async def shutdownbot(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_owner(interaction.user):
            return await interaction.response.send_message("Owner Only, Fuck You.", ephemeral=True)

        await interaction.response.send_message("Shutting down…", ephemeral=True)
        await log_action(self.bot, "Bot Shutdown", f"Triggered by {interaction.user.mention}")
        print(figlet_format("GoodBye!", font="slant"))
        await self.bot.close()
        raise SystemExit(0)

async def setup(bot: commands.Bot):
    await bot.add_cog(Control(bot))