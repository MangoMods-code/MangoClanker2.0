from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.utils.embeds import mango_embed, brand_color
from mangomods_bot.utils.log import log_action

def parse_hex_color(bot, hex_str: str | None) -> discord.Colour:
    if not hex_str or not hex_str.strip():
        return brand_color(bot)
    s = hex_str.strip().replace("#", "")
    try:
        return discord.Colour(int(s, 16))
    except Exception:
        return brand_color(bot)

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.staff_role_id for r in member.roles)

    @app_commands.command(name="echo", description="Send a plain text message as the bot to a channel (staff only).")
    async def echo(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await channel.send(message)
        await log_action(self.bot, "Echo Used", f"By {interaction.user.mention}\nChannel: {channel.mention}\nContent:\n{message}")
        await interaction.response.send_message("Message sent.", ephemeral=True)

    @app_commands.command(name="embed", description="Send a formatted embed as the bot to a channel (staff only).")
    @app_commands.describe(
        channel="Target channel",
        title="Embed title",
        description="Embed description",
        color_hex="Optional hex color like #F9A826",
        image_url="Optional image URL",
        footer_text="Optional footer text"
    )
    async def embed(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str,
        color_hex: str | None = None,
        image_url: str | None = None,
        footer_text: str | None = None
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        emb = discord.Embed(title=title, description=description, colour=parse_hex_color(self.bot, color_hex))
        if image_url and image_url.strip():
            emb.set_image(url=image_url.strip())
        emb.set_footer(text=footer_text.strip() if footer_text and footer_text.strip() else f"MangoMods • {self.bot.config.website_url}")

        await channel.send(embed=emb)
        await log_action(self.bot, "Embed Used", f"By {interaction.user.mention}\nChannel: {channel.mention}\nTitle: **{title}**")
        await interaction.response.send_message("Embed sent.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
