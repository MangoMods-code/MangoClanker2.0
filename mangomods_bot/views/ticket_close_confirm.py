from __future__ import annotations

import discord

class TicketCloseConfirmView(discord.ui.View):
    def __init__(self, bot, channel_id: int) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.channel_id = channel_id

    @discord.ui.button(label="Confirm Close", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self.bot.get_cog("ticket") or self.bot.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("Ticket system not loaded.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await cog.close_ticket(interaction=interaction, channel_id=self.channel_id)
        except Exception as e:
            await interaction.followup.send(f"❌ Close failed: `{type(e).__name__}`", ephemeral=True)
            raise

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Close cancelled.", ephemeral=True)