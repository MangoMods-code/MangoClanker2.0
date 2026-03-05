from __future__ import annotations

import discord

from .ticket_modals import PurchaseTicketModal, SupportTicketModal, GeneralTicketModal

class TicketPanelView(discord.ui.View):
    """
    Persistent panel view. Buttons open modals.
    """
    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Purchase Ticket",
        style=discord.ButtonStyle.success,
        custom_id="mangomods:ticket_panel:purchase"
    )
    async def purchase_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PurchaseTicketModal(self.bot))

    @discord.ui.button(
        label="Support Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="mangomods:ticket_panel:support"
    )
    async def support_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SupportTicketModal(self.bot))

    @discord.ui.button(
        label="General Question",
        style=discord.ButtonStyle.secondary,
        custom_id="mangomods:ticket_panel:general"
    )
    async def general_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GeneralTicketModal(self.bot))