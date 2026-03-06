from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed
from mangomods_bot.utils.log import log_action
from mangomods_bot.utils.misc import iso_now


UPDATE_TYPES = [
    app_commands.Choice(name="Server Sided", value="Server Sided"),
    app_commands.Choice(name="IPA", value="IPA"),
]


class Updates(commands.Cog):
    """
    /updateannounce — post a cheat update announcement and track last-updated
                      per product for the status panel.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store   = JSONStore("/data/updates.json", {"last_updated": {}})
        self.products = JSONStore("/data/products.json", {
            "products": {},
            "meta": {"last_updated_by": None, "last_updated_at": None},
        })

    def _is_staff(self, member: discord.Member) -> bool:
        return any(
            r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id}
            for r in member.roles
        )

    # ── Autocomplete: pull cheat names from products.json ────────────────────

    async def cheat_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        data = await self.products.read()
        products = data.get("products", {})
        names = [info.get("name", k) for k, info in products.items()]
        return [
            app_commands.Choice(name=n, value=n)
            for n in names
            if current.lower() in n.lower()
        ][:25]

    # ── Command ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="updateannounce",
        description="Announce a cheat update and ping the buyer role (staff only).",
    )
    @app_commands.describe(
        cheat="The cheat that was updated",
        update_type="Type of update (Server Sided or IPA)",
        game="The game this cheat is for",
        changelogs="What changed in this update",
        buyer_role="The buyer role to ping",
        description="Optional short description or note",
    )
    @app_commands.choices(update_type=UPDATE_TYPES)
    @app_commands.autocomplete(cheat=cheat_autocomplete)
    async def updateannounce(
        self,
        interaction: discord.Interaction,
        cheat: str,
        update_type: app_commands.Choice[str],
        game: str,
        changelogs: str,
        buyer_role: discord.Role,
        description: str | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        import os
        update_channel_id = int(os.getenv("UPDATE_CHANNEL_ID", "0") or "0")
        if not update_channel_id:
            return await interaction.response.send_message(
                "⚠️ `UPDATE_CHANNEL_ID` is not set in your .env / Railway variables.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(update_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "⚠️ Update channel not found — check `UPDATE_CHANNEL_ID`.",
                ephemeral=True,
            )

        now = datetime.now(timezone.utc)
        unix_ts = int(now.timestamp())

        # ── Build embed ───────────────────────────────────────────────────────
        embed = mango_embed(self.bot)
        embed.title = f"🔔  {cheat} — Update Released"

        if description:
            embed.description = description

        embed.add_field(name="🎮  Game",        value=game,                  inline=True)
        embed.add_field(name="📦  Update Type", value=update_type.value,     inline=True)
        embed.add_field(name="🕐  Released",    value=f"<t:{unix_ts}:F>",    inline=True)

        # Changelogs — split by newline or semicolon for bullet formatting
        lines = [l.strip() for l in changelogs.replace(";", "\n").splitlines() if l.strip()]
        if lines:
            changelog_text = "\n".join(f"• {l}" for l in lines)
        else:
            changelog_text = changelogs
        embed.add_field(name="📋  Changelogs", value=changelog_text, inline=False)

        embed.set_footer(
            text=f"MangoMods  •  Posted by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )

        # ── Send announcement ─────────────────────────────────────────────────
        await interaction.response.send_message(
            f"✅ Update announcement posted for **{cheat}**.", ephemeral=True
        )

        await channel.send(
            content=buyer_role.mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

        # ── Store last-updated timestamp per cheat ───────────────────────────
        data = await self.store.read()
        data.setdefault("last_updated", {})
        data["last_updated"][cheat.strip().lower()] = {
            "name": cheat.strip(),
            "timestamp": now.isoformat(),
            "unix": unix_ts,
            "update_type": update_type.value,
            "game": game,
            "posted_by": interaction.user.display_name,
        }
        await self.store.write(data)

        # ── Refresh status panel to show new last-updated ────────────────────
        status_cog = self.bot.get_cog("status")
        if status_cog and hasattr(status_cog, "refresh_panel"):
            await status_cog.refresh_panel()

        await log_action(
            self.bot,
            "Update Announced",
            f"By {interaction.user.mention}\n"
            f"Cheat: **{cheat}** | Type: **{update_type.value}** | Game: **{game}**",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Updates(bot))
