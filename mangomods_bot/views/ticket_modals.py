from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict

import discord


# ── Field definition ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TicketField:
    embed_name: str
    label: str
    placeholder: str = ""
    style: discord.TextStyle = discord.TextStyle.short
    required: bool = True
    max_length: int = 200


# ── Field sets per ticket type ───────────────────────────────────────────────

PURCHASE_FIELDS: List[TicketField] = [
    TicketField(
        embed_name="Product",
        label="Product You Want To Purchase",
        placeholder="e.g. Aegis CODM, Fluorite FF, Certificate",
        max_length=200,
        required=True,
    ),
    TicketField(
        embed_name="Payment Method",
        label="Payment Method",
        placeholder="PayPal, Cash App, etc.",
        max_length=100,
        required=True,
    ),
    TicketField(
        embed_name="Order ID",
        label="Order ID (if applicable)",
        placeholder="e.g. 12345, or type N/A if none",
        max_length=100,
        required=False,
    ),
    TicketField(
        embed_name="Additional Notes",
        label="Any Additional Notes",
        placeholder="Optional — anything else we should know",
        style=discord.TextStyle.paragraph,
        max_length=800,
        required=False,
    ),
]

SUPPORT_FIELDS: List[TicketField] = [
    TicketField(
        embed_name="Product",
        label="Product You Need Support With",
        placeholder="e.g. Aegis CODM, Fluorite FF, Certificate",
        max_length=200,
        required=True,
    ),
    TicketField(
        embed_name="Order ID / Proof",
        label="Order ID or Proof of Purchase",
        placeholder="Transaction ID, order number, or screenshot description",
        max_length=250,
        required=True,
    ),
    TicketField(
        embed_name="Issue",
        label="Describe Your Issue",
        placeholder="What's going wrong? Be as specific as possible.",
        style=discord.TextStyle.paragraph,
        max_length=1200,
        required=True,
    ),
    TicketField(
        embed_name="Steps Tried",
        label="What Have You Already Tried?",
        placeholder="REQUIRED — list steps you've already attempted",
        style=discord.TextStyle.paragraph,
        max_length=1200,
        required=True,
    ),
]

GENERAL_FIELDS: List[TicketField] = [
    TicketField(
        embed_name="Question",
        label="Your Question",
        placeholder="What would you like to know?",
        style=discord.TextStyle.paragraph,
        max_length=1200,
        required=True,
    ),
    TicketField(
        embed_name="Context",
        label="Any Relevant Context",
        placeholder="Optional — anything that helps us understand your question",
        style=discord.TextStyle.paragraph,
        max_length=1200,
        required=False,
    ),
]


# ── Base modal ───────────────────────────────────────────────────────────────

class BaseTicketModal(discord.ui.Modal):
    """
    Base class for all ticket creation modals.
    Subclasses pass in the ticket type, priority, and field definitions.
    Discord limits modals to 5 TextInput fields.
    """

    def __init__(
        self,
        bot,
        *,
        ticket_type: str,
        priority: str,
        title: str,
        fields: List[TicketField],
    ) -> None:
        if len(fields) > 5:
            raise ValueError("Discord modals support a maximum of 5 input fields.")

        super().__init__(title=title)
        self.bot = bot
        self.ticket_type = ticket_type
        self.priority = priority
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

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog = self.bot.get_cog("ticket") or self.bot.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message(
                "Ticket system is not loaded. Please contact staff.", ephemeral=True
            )

        summary_fields: Dict[str, str] = {}
        for spec in self._specs:
            val = str(self._inputs[spec.embed_name]).strip()
            summary_fields[spec.embed_name] = val if val else "—"

        await cog.create_ticket(
            interaction=interaction,
            ticket_type=self.ticket_type,
            priority=self.priority,
            fields=summary_fields,
        )


# ── Concrete modals ──────────────────────────────────────────────────────────

class PurchaseTicketModal(BaseTicketModal):
    def __init__(self, bot, priority: str = "medium") -> None:
        super().__init__(
            bot,
            ticket_type="purchase",
            priority=priority,
            title="MangoMods — Purchase Ticket",
            fields=PURCHASE_FIELDS,
        )


class SupportTicketModal(BaseTicketModal):
    def __init__(self, bot, priority: str = "medium") -> None:
        super().__init__(
            bot,
            ticket_type="support",
            priority=priority,
            title="MangoMods — Support Ticket",
            fields=SUPPORT_FIELDS,
        )


class GeneralTicketModal(BaseTicketModal):
    def __init__(self, bot, priority: str = "low") -> None:
        super().__init__(
            bot,
            ticket_type="general",
            priority=priority,
            title="MangoMods — General Question",
            fields=GENERAL_FIELDS,
        )
