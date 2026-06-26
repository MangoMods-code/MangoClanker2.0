from __future__ import annotations

import discord


class TicketActionsView(discord.ui.View):
    """
    Persistent view posted inside every ticket channel.
    Row 0 — Staff tools: Claim, Add User, Note
    Row 1 — Ticket lifecycle: Lock, Unlock, Close, Reopen

    locked/closed control which buttons are disabled.
    """

    def __init__(self, bot, *, locked: bool, closed: bool) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.locked = locked
        self.closed = closed

        # Apply disabled states after all buttons are declared
        self.lock_btn.disabled   = locked or closed
        self.unlock_btn.disabled = not locked or closed
        self.close_btn.disabled  = closed
        self.reopen_btn.disabled = not closed

    # ── Row 0: Staff tools ───────────────────────────────────────────────────

    @discord.ui.button(
        label="🏷️  Claim",
        style=discord.ButtonStyle.primary,
        custom_id="mangomods:ticket:claim",
        row=0,
    )
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if cog:
            await cog.claim_ticket(interaction)

    @discord.ui.button(
        label="➕  Add User",
        style=discord.ButtonStyle.secondary,
        custom_id="mangomods:ticket:add_user",
        row=0,
    )
    async def add_user_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if cog:
            await cog.prompt_add_user(interaction)

    @discord.ui.button(
        label="📝  Note",
        style=discord.ButtonStyle.secondary,
        custom_id="mangomods:ticket:note",
        row=0,
    )
    async def note_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if cog:
            await cog.prompt_note(interaction)

    # ── Row 1: Ticket lifecycle ──────────────────────────────────────────────

    @discord.ui.button(
        label="🔒  Lock",
        style=discord.ButtonStyle.secondary,
        custom_id="mangomods:ticket:lock",
        row=1,
    )
    async def lock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if cog:
            await cog.lock_ticket(interaction)

    @discord.ui.button(
        label="🔓  Unlock",
        style=discord.ButtonStyle.success,
        custom_id="mangomods:ticket:unlock",
        row=1,
    )
    async def unlock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if cog:
            await cog.unlock_ticket(interaction)

    @discord.ui.button(
        label="❌  Close",
        style=discord.ButtonStyle.danger,
        custom_id="mangomods:ticket:close",
        row=1,
    )
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if cog:
            await cog.prompt_close_ticket(interaction)

    @discord.ui.button(
        label="♻️  Reopen",
        style=discord.ButtonStyle.primary,
        custom_id="mangomods:ticket:reopen",
        row=1,
    )
    async def reopen_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if cog:
            await cog.reopen_ticket(interaction)
