from __future__ import annotations

import discord

from .ticket_priority import TicketPriorityView

# ── Ticket type options shown in the dropdown ────────────────────────────────

_TICKET_OPTIONS = [
    discord.SelectOption(
        label="Purchase",
        description="Buy a product or service",
        emoji="🛒",
        value="purchase",
    ),
    discord.SelectOption(
        label="Support",
        description="Get help with an existing product",
        emoji="🔧",
        value="support",
    ),
    discord.SelectOption(
        label="General Question",
        description="Ask us anything else",
        emoji="💬",
        value="general",
    ),
]

_TYPE_META: dict[str, tuple[str, str]] = {
    "purchase": ("🛒", "Purchase"),
    "support":  ("🔧", "Support"),
    "general":  ("💬", "General Question"),
}

_PRIORITY_DESC = (
    "Select how urgent your ticket is:\n\n"
    "🟢 **Low** — No rush, general enquiry\n"
    "🟡 **Medium** — Needs attention soon\n"
    "🔴 **High** — Urgent or time-sensitive\n"
    "🚨 **Urgent** — Critical issue, needs immediate help"
)


# ── Select component ─────────────────────────────────────────────────────────

class TicketTypeSelect(discord.ui.Select):
    """
    Persistent select menu on the ticket panel.
    Selecting a type shows an ephemeral priority picker.
    """

    def __init__(self, bot) -> None:
        self.bot = bot
        super().__init__(
            placeholder="📋  Select a ticket type to open...",
            options=_TICKET_OPTIONS,
            custom_id="mangomods:ticket_panel:type_select",
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket_type = self.values[0]
        emoji, label = _TYPE_META.get(ticket_type, ("🎫", ticket_type.title()))

        emb = discord.Embed(
            title=f"{emoji}  {label} Ticket — Select Priority",
            description=_PRIORITY_DESC,
            colour=discord.Colour(0xF9A826),
        )
        emb.set_footer(text="MangoMods  •  Step 2 of 3 — Priority")

        await interaction.response.send_message(
            embed=emb,
            view=TicketPriorityView(self.bot, ticket_type),
            ephemeral=True,
        )


# ── Panel view ───────────────────────────────────────────────────────────────

class TicketPanelView(discord.ui.View):
    """
    Persistent view posted to the ticket channel via /ticket panel.
    Contains a single Select menu for ticket type.
    """

    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketTypeSelect(bot))
