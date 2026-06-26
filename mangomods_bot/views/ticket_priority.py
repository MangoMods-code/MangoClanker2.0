from __future__ import annotations

import discord

from .ticket_modals import PurchaseTicketModal, SupportTicketModal, GeneralTicketModal

# Maps priority key -> (button label, button style)
PRIORITY_STYLES: dict[str, tuple[str, discord.ButtonStyle]] = {
    "low":    ("🟢  Low",    discord.ButtonStyle.success),
    "medium": ("🟡  Medium", discord.ButtonStyle.primary),
    "high":   ("🔴  High",   discord.ButtonStyle.danger),
    "urgent": ("🚨  Urgent", discord.ButtonStyle.danger),
}

# Maps ticket type -> the modal class to open
MODAL_MAP = {
    "purchase": PurchaseTicketModal,
    "support":  SupportTicketModal,
    "general":  GeneralTicketModal,
}


class TicketPriorityView(discord.ui.View):
    """
    Ephemeral view shown after the user selects a ticket type from the panel.
    The user picks a priority level, which then opens the appropriate modal.
    Not persistent — ephemeral messages disappear after the modal opens anyway.
    """

    def __init__(self, bot, ticket_type: str) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.ticket_type = ticket_type

        for priority_key, (label, style) in PRIORITY_STYLES.items():
            btn = discord.ui.Button(label=label, style=style)
            btn.callback = self._make_callback(priority_key)
            self.add_item(btn)

    def _make_callback(self, priority: str):
        """Creates a unique callback for each priority button."""
        async def callback(interaction: discord.Interaction) -> None:
            modal_cls = MODAL_MAP.get(self.ticket_type)
            if not modal_cls:
                return await interaction.response.send_message(
                    "Unknown ticket type. Please try again.", ephemeral=True
                )
            await interaction.response.send_modal(modal_cls(self.bot, priority=priority))

        return callback
