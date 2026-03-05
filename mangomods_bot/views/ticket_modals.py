from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict

import discord


# ----------------------------
# EASY FIELD CUSTOMIZATION
# ----------------------------
# Discord hard limit: max 5 inputs per modal.
# Add/remove fields here, and set required=True/False.

@dataclass(frozen=True)
class TicketField:
    # Name used in the ticket summary embed
    embed_name: str
    # Label shown in the modal input UI
    label: str
    placeholder: str = ""
    style: discord.TextStyle = discord.TextStyle.short
    required: bool = True
    max_length: int = 200


PURCHASE_FIELDS: List[TicketField] = [
    TicketField(embed_name="Product", label="Product You Want To Purchase", placeholder="e.g. Product Name / Service", max_length=200, required=True),
    TicketField(embed_name="Payment Method", label="Payment Method", placeholder="PayPal, Cashapp, etc.", max_length=100, required=True),
    TicketField(embed_name="Order ID", label="Order ID", placeholder="e.g. 12345 or N if none", max_length=100, required=True),
    TicketField(embed_name="Additional Notes", label="Any Additional Notes", placeholder="Optional details", style=discord.TextStyle.paragraph, max_length=800, required=False),
]

SUPPORT_FIELDS: List[TicketField] = [
    TicketField(embed_name="Product", label="Product You Need Support With", placeholder="e.g. Product Name / Service", max_length=200, required=True),
    TicketField(embed_name="Order ID / Proof", label="Order ID or Proof of Purchase", placeholder="Order # / Transaction / Proof details", max_length=250, required=True),
    TicketField(embed_name="Issue", label="Description of Your Issue", placeholder="Explain what's happening", style=discord.TextStyle.paragraph, max_length=1200, required=True),
    TicketField(embed_name="Steps Already Tried", label="Steps Already Tried", placeholder="REQUIRED: what you've attempted", style=discord.TextStyle.paragraph, max_length=1200, required=True),
]

GENERAL_FIELDS: List[TicketField] = [
    TicketField(embed_name="Question", label="Your Question", placeholder="What can we help with?", style=discord.TextStyle.paragraph, max_length=1200, required=True),
    TicketField(embed_name="Context", label="Any Relevant Context", placeholder="Optional details", style=discord.TextStyle.paragraph, max_length=1200, required=False),
]


class BaseTicketModal(discord.ui.Modal):
    def __init__(self, bot, *, ticket_type: str, title: str, fields: List[TicketField]) -> None:
        if len(fields) > 5:
            raise ValueError("Discord allows a maximum of 5 TextInput fields per modal.")

        super().__init__(title=title)
        self.bot = bot
        self.ticket_type = ticket_type
        self._specs = fields
        self._inputs: Dict[str, discord.ui.TextInput] = {}

        for spec in fields:
            ti = discord.ui.TextInput(
                label=spec.label,
                placeholder=spec.placeholder,
                style=spec.style,
                required=spec.required,
                max_length=spec.max_length,
            )
            self._inputs[spec.embed_name] = ti
            self.add_item(ti)

    async def on_submit(self, interaction: discord.Interaction):
        cog = self.bot.get_cog("ticket") or self.bot.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("Ticket system is not loaded.", ephemeral=True)

        summary_fields: Dict[str, str] = {}
        for spec in self._specs:
            val = str(self._inputs[spec.embed_name]).strip()
            summary_fields[spec.embed_name] = val if val else "—"

        await cog.create_ticket(
            interaction=interaction,
            ticket_type=self.ticket_type,
            fields=summary_fields,
        )


class PurchaseTicketModal(BaseTicketModal):
    def __init__(self, bot) -> None:
        super().__init__(
            bot,
            ticket_type="purchase",
            title="MangoMods — Purchase Ticket",
            fields=PURCHASE_FIELDS,
        )


class SupportTicketModal(BaseTicketModal):
    def __init__(self, bot) -> None:
        super().__init__(
            bot,
            ticket_type="support",
            title="MangoMods — Support Ticket",
            fields=SUPPORT_FIELDS,
        )


class GeneralTicketModal(BaseTicketModal):
    def __init__(self, bot) -> None:
        super().__init__(
            bot,
            ticket_type="general",
            title="MangoMods — General Question",
            fields=GENERAL_FIELDS,
        )