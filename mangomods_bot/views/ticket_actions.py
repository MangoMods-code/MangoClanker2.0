from __future__ import annotations
import discord

class TicketActionsView(discord.ui.View):
    def __init__(self, bot, *, locked: bool, closed: bool) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.locked = locked
        self.closed = closed

        # Row 0: Lock/Unlock + Close/Reopen
        self.lock_btn.disabled = locked
        self.unlock_btn.disabled = not locked

        self.close_btn.disabled = closed
        self.reopen_btn.disabled = not closed

    # ---- Lock / Unlock ----
    @discord.ui.button(label="Lock", style=discord.ButtonStyle.secondary, custom_id="mangomods:ticket:lock", row=0)
    async def lock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("Ticket system not loaded.", ephemeral=True)
        await cog.lock_ticket(interaction)

    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.success, custom_id="mangomods:ticket:unlock", row=0)
    async def unlock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("Ticket system not loaded.", ephemeral=True)
        await cog.unlock_ticket(interaction)

    # ---- Close / Reopen ----
    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="mangomods:ticket:close", row=0)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("Ticket system not loaded.", ephemeral=True)
        await cog.prompt_close_ticket(interaction)

    @discord.ui.button(label="Reopen", style=discord.ButtonStyle.primary, custom_id="mangomods:ticket:reopen", row=0)
    async def reopen_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("Ticket system not loaded.", ephemeral=True)
        await cog.reopen_ticket(interaction)

    # ---- Claim / Add user ----
    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, custom_id="mangomods:ticket:claim", row=1)
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("Ticket system not loaded.", ephemeral=True)
        await cog.claim_ticket(interaction)

    @discord.ui.button(label="Add User", style=discord.ButtonStyle.secondary, custom_id="mangomods:ticket:add_user", row=1)
    async def add_user_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("Ticket system not loaded.", ephemeral=True)
        await cog.prompt_add_user(interaction)