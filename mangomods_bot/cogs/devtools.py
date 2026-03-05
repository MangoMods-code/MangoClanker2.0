from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.utils.log import log_action


class DevTools(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.staff_role_id for r in member.roles)

    def _ext_name(self, short: str) -> str:
        """
        Allows:
          /reloadcog tickets
        -> mangomods_bot.cogs.tickets
        Also allows full extension path.
        """
        short = short.strip()
        if short.startswith("mangomods_bot."):
            return short
        if short.startswith("cogs."):
            return f"mangomods_bot.{short}"
        # common case: "tickets", "vouch", "mute", etc.
        return f"mangomods_bot.cogs.{short}"

    @app_commands.command(name="reloadcog", description="Reload a bot cog (staff only).")
    @app_commands.describe(name="Cog name, e.g. tickets, vouch, mute, status, welcome, admin")
    async def reloadcog(self, interaction: discord.Interaction, name: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        ext = self._ext_name(name)
        try:
            # reload is available in discord.py 2.x
            await self.bot.reload_extension(ext)
            await log_action(self.bot, "Cog Reloaded", f"By {interaction.user.mention}\nReloaded: `{ext}`")
            return await interaction.followup.send(f"✅ Reloaded `{ext}`", ephemeral=True)
        except Exception as e:
            await log_action(self.bot, "Cog Reload Failed", f"By {interaction.user.mention}\nTarget: `{ext}`\nError: `{type(e).__name__}: {e}`")
            return await interaction.followup.send(f"❌ Failed to reload `{ext}`:\n`{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(name="reloadallcogs", description="Reload all bot cogs (staff only).")
    async def reloadallcogs(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        # Reload only your cogs
        targets = [ext for ext in list(self.bot.extensions.keys()) if ext.startswith("mangomods_bot.cogs.")]
        ok, failed = [], []

        for ext in targets:
            try:
                await self.bot.reload_extension(ext)
                ok.append(ext)
            except Exception as e:
                failed.append((ext, f"{type(e).__name__}: {e}"))

        await log_action(
            self.bot,
            "Reload All Cogs",
            f"By {interaction.user.mention}\nOK: {len(ok)}\nFailed: {len(failed)}"
        )

        msg = f"✅ Reloaded **{len(ok)}** cogs."
        if failed:
            msg += "\n\n❌ Failed:\n" + "\n".join([f"- `{ext}` — `{err}`" for ext, err in failed])

        await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DevTools(bot))