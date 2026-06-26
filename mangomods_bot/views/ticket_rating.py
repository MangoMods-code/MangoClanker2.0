from __future__ import annotations

import discord


class TicketRatingView(discord.ui.View):
    """
    Sent to the ticket owner via DM after their ticket is closed.
    Lets them rate their support experience from 1 to 5 stars.
    Non-persistent (24h timeout) — users typically rate right after close.
    """

    def __init__(self, bot, ticket_channel_id: int) -> None:
        super().__init__(timeout=86400)  # 24 hours
        self.bot = bot
        self.ticket_channel_id = ticket_channel_id
        self._rated = False

        star_labels = ["⭐  1", "⭐⭐  2", "⭐⭐⭐  3", "⭐⭐⭐⭐  4", "⭐⭐⭐⭐⭐  5"]
        for i, label in enumerate(star_labels, start=1):
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, rating: int):
        async def callback(interaction: discord.Interaction) -> None:
            if self._rated:
                return await interaction.response.send_message(
                    "You've already rated this ticket.", ephemeral=False
                )

            self._rated = True

            # Disable all buttons so it can't be submitted twice
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            stars = "⭐" * rating
            await interaction.response.edit_message(
                content=(
                    f"✅ **Rating received — thank you!**\n"
                    f"You gave your support experience **{stars}** ({rating}/5).\n\n"
                    f"*Your feedback helps us improve.*"
                ),
                view=self,
            )

            # Store the rating in ticket state via the cog
            cog = interaction.client.get_cog("ticket") or interaction.client.get_cog("Tickets")
            if cog:
                await cog.record_rating(self.ticket_channel_id, rating)

        return callback
