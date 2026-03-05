from __future__ import annotations

import os
import discord
from discord.ext import commands
from discord import app_commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.log import log_action
from mangomods_bot.utils.embeds import mango_embed


def _int_env(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)) or str(default))
    except Exception:
        return default


# ──────────────────────────────────────────────────────────────────────────────
# View
# ──────────────────────────────────────────────────────────────────────────────

class PromoView(discord.ui.View):
    """Persistent view with a Shop Now link button."""

    def __init__(self, website_url: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="🛒  Shop Now",
                style=discord.ButtonStyle.link,
                url=website_url,
            )
        )


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────

class Promos(commands.Cog):
    """
    Promo code announcements.

    Commands:
      /promo announce  — post a new promo code embed to the promo channel.
      /promo end       — mark an active promo as expired (edits the original message).
      /promo list      — show all currently active promos (ephemeral, staff only).
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store = JSONStore("/data/promos.json", {"active": {}})
        self.promo_channel_id = _int_env("PROMO_CHANNEL_ID")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _website_url(self) -> str:
        return getattr(self.bot.config, "website_url", "https://mangomods.store")

    def _is_staff(self, member: discord.Member) -> bool:
        staff_id = getattr(self.bot.config, "staff_role_id", None)
        owner_id = getattr(self.bot.config, "owner_role_id", None)
        return any(r.id in {staff_id, owner_id} for r in member.roles)

    def _build_promo_embed(
        self,
        code: str,
        discount: str | None,
        description: str | None,
        expires: str | None,
        expired: bool = False,
    ) -> discord.Embed:
        embed = mango_embed(self.bot)

        if expired:
            embed.title = "🚫  Promo Expired"
            embed.colour = discord.Colour.dark_grey()
        else:
            embed.title = "🎉  New Promo Code!"

        # Code field — big and obvious
        embed.add_field(
            name="Promo Code",
            value=f"```{code}```",
            inline=False,
        )

        if discount:
            embed.add_field(name="Discount", value=discount, inline=True)

        if expires:
            label = "~~Expires~~" if expired else "Expires"
            embed.add_field(name=label, value=f"~~{expires}~~" if expired else expires, inline=True)

        if description:
            embed.add_field(name="Details", value=description, inline=False)

        if expired:
            embed.set_footer(text="MangoMods  •  This promo has ended")
        else:
            embed.set_footer(text="MangoMods  •  Use the code at checkout")

        return embed

    # ── command group ─────────────────────────────────────────────────────────

    promo_group = app_commands.Group(name="promo", description="Promo code management (staff only).")

    @promo_group.command(name="announce", description="Announce a promo code to the promo channel.")
    @app_commands.describe(
        code="The promo code (e.g. MANGO20)",
        discount="What the discount is (e.g. 20% off, Free shipping)",
        description="Optional extra details (e.g. Valid on all products)",
        expires="Optional expiry info (e.g. 24 hours, Sunday midnight)",
        ping="Optional role or @everyone to ping with the announcement",
    )
    async def promo_announce(
        self,
        interaction: discord.Interaction,
        code: str,
        discount: str | None = None,
        description: str | None = None,
        expires: str | None = None,
        ping: discord.Role | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        if not self.promo_channel_id:
            return await interaction.response.send_message(
                "⚠️ `PROMO_CHANNEL_ID` is not set in your .env.", ephemeral=True
            )

        channel = interaction.guild.get_channel(self.promo_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "⚠️ Promo channel not found — check `PROMO_CHANNEL_ID` in .env.", ephemeral=True
            )

        embed = self._build_promo_embed(
            code=code.upper(),
            discount=discount,
            description=description,
            expires=expires,
        )

        view = PromoView(self._website_url())

        # Build ping content
        content = None
        if ping:
            if ping.is_default():  # @everyone
                content = "@everyone"
            else:
                content = ping.mention

        msg = await channel.send(content=content, embed=embed, view=view)

        # Persist active promo
        data = await self.store.read()
        data.setdefault("active", {})
        data["active"][str(msg.id)] = {
            "code": code.upper(),
            "discount": discount,
            "description": description,
            "expires": expires,
            "channel_id": channel.id,
            "announced_by": interaction.user.id,
        }
        await self.store.write(data)

        await log_action(
            self.bot,
            "Promo Announced",
            f"Staff: {interaction.user.mention}\n"
            f"Code: `{code.upper()}`"
            + (f"\nDiscount: {discount}" if discount else "")
            + (f"\nExpires: {expires}" if expires else ""),
        )

        await interaction.response.send_message(
            f"✅ Promo `{code.upper()}` posted to {channel.mention}.", ephemeral=True
        )

    @promo_group.command(name="end", description="Mark an active promo as expired.")
    @app_commands.describe(code="The promo code to expire (e.g. MANGO20)")
    async def promo_end(self, interaction: discord.Interaction, code: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        data = await self.store.read()
        active = data.get("active", {})

        # Find the promo by code (case-insensitive)
        match_id = None
        match_data = None
        for msg_id, promo in active.items():
            if promo.get("code", "").upper() == code.upper():
                match_id = msg_id
                match_data = promo
                break

        if not match_id or not match_data:
            return await interaction.response.send_message(
                f"❌ No active promo found with code `{code.upper()}`.\n"
                f"Use `/promo list` to see active promos.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(match_data["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "⚠️ Original promo channel not found.", ephemeral=True
            )

        try:
            msg = await channel.fetch_message(int(match_id))
        except discord.NotFound:
            # Message was deleted — just remove from store
            data["active"].pop(match_id)
            await self.store.write(data)
            return await interaction.response.send_message(
                f"⚠️ Original message was deleted. Removed `{code.upper()}` from active promos.",
                ephemeral=True,
            )

        # Edit the embed to show expired state
        expired_embed = self._build_promo_embed(
            code=match_data["code"],
            discount=match_data.get("discount"),
            description=match_data.get("description"),
            expires=match_data.get("expires"),
            expired=True,
        )

        # Replace view with a disabled-looking version (no button)
        await msg.edit(embed=expired_embed, view=None)

        # Remove from active store
        data["active"].pop(match_id)
        await self.store.write(data)

        await log_action(
            self.bot,
            "Promo Ended",
            f"Staff: {interaction.user.mention}\nCode: `{match_data['code']}`",
        )

        await interaction.response.send_message(
            f"✅ Promo `{match_data['code']}` marked as expired.", ephemeral=True
        )

    @promo_group.command(name="list", description="List all currently active promo codes.")
    async def promo_list(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        data = await self.store.read()
        active = data.get("active", {})

        if not active:
            return await interaction.response.send_message(
                "No active promos right now.", ephemeral=True
            )

        embed = mango_embed(self.bot)
        embed.title = "🎟️  Active Promo Codes"

        for promo in active.values():
            value_parts = []
            if promo.get("discount"):
                value_parts.append(f"Discount: {promo['discount']}")
            if promo.get("expires"):
                value_parts.append(f"Expires: {promo['expires']}")
            if promo.get("description"):
                value_parts.append(f"Details: {promo['description']}")
            value = "\n".join(value_parts) if value_parts else "No extra details."
            embed.add_field(name=f"`{promo['code']}`", value=value, inline=False)

        embed.set_footer(text=f"MangoMods  •  {len(active)} active promo(s)")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Promos(bot))