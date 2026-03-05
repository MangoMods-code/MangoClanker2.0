from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed
from mangomods_bot.utils.log import log_action
from mangomods_bot.utils.misc import iso_now, pretty_dt

STATUS_MAP = {
    "undetected": ("🟢", "Undetected — Safe to use"),
    "risk": ("🟠", "Use at Own Risk — Caution advised"),
    "detected": ("🔴", "Detected — Do not use"),
    "testing": ("🔵", "Testing — Integrity testing in progress"),
}

def normalize_status(s: str) -> str:
    s = (s or "").lower().strip()
    if s in STATUS_MAP:
        return s
    # allow some aliases
    if s in {"use at own risk", "caution", "caution advised"}:
        return "risk"
    return s

class StatusPanel(commands.GroupCog, name="status"):
    """
    /status panel -> posts persistent embed in STATUS_CHANNEL_ID.
    """
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.products = JSONStore("/data/products.json", {
            "products": {},
            "meta": {"last_updated_by": None, "last_updated_at": None}
        })
        self.panels = JSONStore("/data/panels.json", {
            "ticket_panel": None,
            "status_panel": None
        })

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.staff_role_id for r in member.roles)

    async def _build_embed(self) -> discord.Embed:
        data = await self.products.read()
        products = data.get("products", {})

        emb = mango_embed(
            self.bot,
            title="📌 MangoMods — Product Status",
            description=f"Live detection status for MangoMods products.\nWebsite: **{self.bot.config.website_url}**"
        )

        if not products:
            emb.add_field(name="No products yet", value="Staff can add products using `/addproduct`.", inline=False)
        else:
            lines = []
            # sort by display name
            items = sorted(products.items(), key=lambda kv: kv[1].get("name", kv[0]).lower())
            for _, info in items:
                name = info.get("name", "Unknown Product")
                st = info.get("status", "testing")
                emoji, label = STATUS_MAP.get(st, ("⚪", "Unknown"))
                lines.append(f"{emoji} **{name}** — {label}")
            emb.add_field(name="Current Status", value="\n".join(lines), inline=False)

        meta = data.get("meta", {})
        lu_by = meta.get("last_updated_by")
        lu_at = meta.get("last_updated_at")
        if lu_by and lu_at:
            emb.set_footer(text=f"Last updated by {lu_by} on {pretty_dt(lu_at)}")
        else:
            emb.set_footer(text="Last updated by —")

        return emb

    async def refresh_panel(self) -> None:
        panels = await self.panels.read()
        panel = panels.get("status_panel")
        channel_id = self.bot.config.status_channel_id

        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        emb = await self._build_embed()

        if panel:
            try:
                msg = await channel.fetch_message(int(panel["message_id"]))
                await msg.edit(embed=emb)
                return
            except Exception:
                # message deleted or inaccessible -> re-post
                pass

        msg = await channel.send(embed=emb)
        panels["status_panel"] = {"channel_id": channel.id, "message_id": msg.id}
        await self.panels.write(panels)

    @app_commands.command(name="panel", description="Post/refresh the MangoMods product status panel.")
    async def panel(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await self.refresh_panel()
        await log_action(self.bot, "Status Panel Refreshed", f"By {interaction.user.mention}")
        await interaction.response.send_message("Status panel posted/refreshed.", ephemeral=True)

class StatusCommands(commands.Cog):
    """
    Root-level staff commands:
    /addproduct
    /removeproduct
    /updatestatus
    """
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.products = JSONStore("data/products.json", {
            "products": {},
            "meta": {"last_updated_by": None, "last_updated_at": None}
        })

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.staff_role_id for r in member.roles)

    def _key(self, name: str) -> str:
        return name.strip().lower()

    async def _touch_meta(self, staff: discord.Member) -> None:
        data = await self.products.read()
        data.setdefault("meta", {})
        data["meta"]["last_updated_by"] = staff.display_name
        data["meta"]["last_updated_at"] = iso_now()
        await self.products.write(data)

    async def _refresh_status_panel(self) -> None:
        cog = self.bot.get_cog("StatusPanel")
        # GroupCog name is class name unless overridden; discord.py uses class name by default.
        # We added StatusPanel as a cog, so we can fetch by class name.
        if cog and hasattr(cog, "refresh_panel"):
            await cog.refresh_panel()  # type: ignore[attr-defined]

    @app_commands.command(name="addproduct", description="Add a product to the status board.")
    @app_commands.describe(name="Product name", status="undetected/risk/detected/testing")
    async def addproduct(self, interaction: discord.Interaction, name: str, status: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        st = normalize_status(status)
        if st not in STATUS_MAP:
            return await interaction.response.send_message(
                "Invalid status. Use: undetected, risk, detected, testing.",
                ephemeral=True
            )

        data = await self.products.read()
        data.setdefault("products", {})
        key = self._key(name)
        if key in data["products"]:
            return await interaction.response.send_message("That product already exists. Use `/updatestatus`.", ephemeral=True)

        data["products"][key] = {"name": name.strip(), "status": st}
        data.setdefault("meta", {})
        data["meta"]["last_updated_by"] = interaction.user.display_name
        data["meta"]["last_updated_at"] = iso_now()
        await self.products.write(data)

        await self._refresh_status_panel()
        await log_action(self.bot, "Product Added", f"By {interaction.user.mention}\n**{name.strip()}** -> **{st}**")
        await interaction.response.send_message("Product added and panel updated.", ephemeral=True)

    @app_commands.command(name="removeproduct", description="Remove a product from the status board.")
    @app_commands.describe(name="Product name to remove")
    async def removeproduct(self, interaction: discord.Interaction, name: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        data = await self.products.read()
        key = self._key(name)
        if key not in data.get("products", {}):
            return await interaction.response.send_message("Product not found.", ephemeral=True)

        removed = data["products"].pop(key)
        data.setdefault("meta", {})
        data["meta"]["last_updated_by"] = interaction.user.display_name
        data["meta"]["last_updated_at"] = iso_now()
        await self.products.write(data)

        await self._refresh_status_panel()
        await log_action(self.bot, "Product Removed", f"By {interaction.user.mention}\nRemoved **{removed.get('name','(unknown)')}**")
        await interaction.response.send_message("Product removed and panel updated.", ephemeral=True)

    @app_commands.command(name="updatestatus", description="Update a product's status on the status board.")
    @app_commands.describe(product="Product name", status="undetected/risk/detected/testing")
    async def updatestatus(self, interaction: discord.Interaction, product: str, status: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        st = normalize_status(status)
        if st not in STATUS_MAP:
            return await interaction.response.send_message(
                "Invalid status. Use: undetected, risk, detected, testing.",
                ephemeral=True
            )

        data = await self.products.read()
        key = self._key(product)
        if key not in data.get("products", {}):
            return await interaction.response.send_message("Product not found.", ephemeral=True)

        data["products"][key]["status"] = st
        data.setdefault("meta", {})
        data["meta"]["last_updated_by"] = interaction.user.display_name
        data["meta"]["last_updated_at"] = iso_now()
        await self.products.write(data)

        await self._refresh_status_panel()
        await log_action(self.bot, "Status Updated", f"By {interaction.user.mention}\n**{product.strip()}** -> **{st}**")
        await interaction.response.send_message("Status updated and panel refreshed.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(StatusPanel(bot))
    await bot.add_cog(StatusCommands(bot))