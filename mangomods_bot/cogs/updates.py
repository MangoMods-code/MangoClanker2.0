from __future__ import annotations

import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed
from mangomods_bot.utils.log import log_action
from mangomods_bot.utils.misc import iso_now


UPDATE_TYPES = [
    app_commands.Choice(name="Server Sided", value="Server Sided"),
    app_commands.Choice(name="IPA",          value="IPA"),
    app_commands.Choice(name="Patch",        value="Patch"),
    app_commands.Choice(name="Hotfix",       value="Hotfix"),
]


class Updates(commands.Cog):
    """
    /updateannounce — post a cheat update announcement, ping the buyer role,
                      store last-updated timestamp, and refresh the status panel.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot      = bot
        self.store    = JSONStore("/data/updates.json",  {"last_updated": {}})
        self.products = JSONStore("/data/products.json", {
            "products": {},
            "meta": {"last_updated_by": None, "last_updated_at": None},
        })

    def _is_staff(self, member: discord.Member) -> bool:
        return any(
            r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id}
            for r in member.roles
        )

    # ── Autocomplete ──────────────────────────────────────────────────────────

    async def _cheat_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        data  = await self.products.read()
        names = [info.get("name", k) for k, info in data.get("products", {}).items()]
        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()
        ][:25]

    # ── /updateannounce ───────────────────────────────────────────────────────

    @app_commands.command(
        name="updateannounce",
        description="Announce a cheat update and ping the buyer role. Staff only.",
    )
    @app_commands.describe(
        cheat="The cheat that was updated (autocompleted from product list)",
        update_type="Type of update",
        game="Game this cheat is for",
        version="New version number after this update (e.g. 2.4.1)",
        changelogs="What changed — separate multiple lines with a semicolon",
        description="Optional short note shown at the top of the embed",
    )
    @app_commands.choices(update_type=UPDATE_TYPES)
    @app_commands.autocomplete(cheat=_cheat_autocomplete)
    async def updateannounce(
        self,
        interaction: discord.Interaction,
        cheat: str,
        update_type: app_commands.Choice[str],
        game: str,
        changelogs: str,
        version: str | None = None,
        description: str | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        update_channel_id = int(os.getenv("UPDATE_CHANNEL_ID", "0") or "0")
        if not update_channel_id:
            return await interaction.response.send_message(
                "⚠️ `UPDATE_CHANNEL_ID` is not set in your .env.", ephemeral=True
            )

        channel = interaction.guild.get_channel(update_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "⚠️ Update channel not found — check `UPDATE_CHANNEL_ID`.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        now     = datetime.now(timezone.utc)
        unix_ts = int(now.timestamp())

        # Resolve buyer role from products.json if one is stored
        prod_data    = await self.products.read()
        prod_key     = cheat.strip().lower()
        prod_info    = prod_data.get("products", {}).get(prod_key, {})
        buyer_role_id = prod_info.get("buyer_role_id")
        buyer_role    = interaction.guild.get_role(int(buyer_role_id)) if buyer_role_id else None

        # If version provided, update it in products.json
        if version and prod_key in prod_data.get("products", {}):
            clean_ver = version.strip().lstrip("v")
            prod_data["products"][prod_key]["version"] = clean_ver
            prod_data.setdefault("meta", {})
            prod_data["meta"]["last_updated_by"] = interaction.user.display_name
            prod_data["meta"]["last_updated_at"] = iso_now()
            await self.products.write(prod_data)

        # ── Build embed ───────────────────────────────────────────────────────
        emb = mango_embed(self.bot)
        emb.title = f"🔔  {cheat} — Update Released"

        if description:
            emb.description = description

        # Version field — use provided, fall back to what's stored, or omit
        display_version = version or prod_info.get("version")

        emb.add_field(name="🎮  Game",        value=game,                inline=True)
        emb.add_field(name="📦  Update Type", value=update_type.value,   inline=True)

        if display_version:
            emb.add_field(name="🏷️  Version", value=f"v{display_version.lstrip('v')}", inline=True)

        emb.add_field(name="🕐  Released", value=f"<t:{unix_ts}:F>", inline=True)

        # Changelogs — semicolon or newline separated → bullet list
        lines = [l.strip() for l in changelogs.replace(";", "\n").splitlines() if l.strip()]
        changelog_text = "\n".join(f"• {l}" for l in lines) if lines else changelogs
        emb.add_field(name="📋  Changelogs", value=changelog_text, inline=False)

        emb.set_footer(
            text=f"MangoMods  •  Posted by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )

        # ── Post announcement ─────────────────────────────────────────────────
        ping_content = buyer_role.mention if buyer_role else ""
        await channel.send(
            content=ping_content or None,
            embed=emb,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

        # ── Store last-updated per cheat ──────────────────────────────────────
        upd_data = await self.store.read()
        upd_data.setdefault("last_updated", {})
        upd_data["last_updated"][prod_key] = {
            "name":        cheat.strip(),
            "timestamp":   now.isoformat(),
            "unix":        unix_ts,
            "update_type": update_type.value,
            "game":        game,
            "version":     display_version or "",
            "posted_by":   interaction.user.display_name,
        }
        await self.store.write(upd_data)

        # ── Refresh status panel ──────────────────────────────────────────────
        status_cog = self.bot.get_cog("status")
        if status_cog and hasattr(status_cog, "refresh_panel"):
            await status_cog.refresh_panel()

        await log_action(
            self.bot,
            "Update Announced",
            f"By {interaction.user.mention}\n"
            f"Cheat: **{cheat}** | Type: **{update_type.value}** | Game: **{game}**"
            + (f" | Version: **v{display_version}**" if display_version else "")
            + (f" | Pinged: {buyer_role.mention}" if buyer_role else " | No buyer role configured"),
        )

        ver_note = f" | Version set to `v{display_version.lstrip('v')}`" if display_version else ""
        await interaction.followup.send(
            f"✅ Update for **{cheat}** posted in {channel.mention}{ver_note}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Updates(bot))
