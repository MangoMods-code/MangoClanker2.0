from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed
from mangomods_bot.utils.log import log_action
from mangomods_bot.utils.misc import iso_now, pretty_dt

# ── Status definitions ────────────────────────────────────────────────────────

STATUS_MAP: dict[str, tuple[str, str, int]] = {
    #  key          emoji   label                                  embed colour
    "undetected": ("🟢", "Undetected — Safe to use",              0x57F287),
    "risk":       ("🟠", "Use at Own Risk — Bans Reported",       0xF9A826),
    "detected":   ("🔴", "Detected — Do not use, Updating",       0xED4245),
    "testing":    ("⚪", "Testing — Integrity check in progress", 0x95A5A6),
    "revokes":    ("🔵", "Revokes Tracked — See description",     0x5865F2),
}

STATUS_ALIASES: dict[str, str] = {
    "use at own risk": "risk",
    "caution":         "risk",
    "safe":            "undetected",
    "update":          "detected",
    "updating":        "detected",
}


def normalize_status(s: str) -> str:
    s = (s or "").lower().strip()
    return STATUS_ALIASES.get(s, s) if s not in STATUS_MAP else s


def _status_emoji(status: str) -> str:
    return STATUS_MAP.get(status, ("⚪", "", 0))[0]


def _status_label(status: str) -> str:
    return STATUS_MAP.get(status, ("⚪", "Unknown", 0))[1]


def _status_color(status: str) -> int:
    return STATUS_MAP.get(status, ("⚪", "", 0xF9A826))[2]


# ──────────────────────────────────────────────────────────────────────────────
# StatusPanel  (GroupCog — /status panel)
# ──────────────────────────────────────────────────────────────────────────────

class StatusPanel(commands.GroupCog, name="status"):
    """
    /status panel  — post or refresh the live product status embed.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot      = bot
        self.products = JSONStore("/data/products.json", {
            "products": {},
            "meta":     {"last_updated_by": None, "last_updated_at": None},
        })
        self.panels  = JSONStore("/data/panels.json",  {"ticket_panel": None, "status_panel": None})
        self.updates = JSONStore("/data/updates.json", {"last_updated": {}})

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id}
                   for r in member.roles)

    # ── Embed builder ─────────────────────────────────────────────────────────

    async def _build_embed(self) -> discord.Embed:
        data     = await self.products.read()
        upd_data = await self.updates.read()
        products = data.get("products", {})
        last_upd = upd_data.get("last_updated", {})

        # Overall embed colour — red if anything detected, gold otherwise
        any_detected = any(
            info.get("status") == "detected" for info in products.values()
        )
        embed_color = 0xED4245 if any_detected else 0xF9A826

        emb = discord.Embed(
            colour    = discord.Colour(embed_color),
            timestamp = datetime.now(timezone.utc),
        )

        emb.set_author(
            name     = "MangoMods — Live Product Status",
            icon_url = self.bot.config.website_url or None,
        )

        if not products:
            emb.description = "No products listed yet. Staff can add products with `/addproduct`."
            emb.set_footer(text="MangoMods  •  Product Status")
            return emb

        # ── Group products by status ──────────────────────────────────────────
        # Order: undetected → risk → testing → revokes → detected
        STATUS_ORDER = ["undetected", "risk", "testing", "revokes", "detected"]

        grouped: dict[str, list[dict]] = {k: [] for k in STATUS_ORDER}
        for info in products.values():
            st = info.get("status", "testing")
            grouped.setdefault(st, []).append(info)

        # Sort each group alphabetically by product name
        for st in grouped:
            grouped[st].sort(key=lambda x: x.get("name", "").lower())

        # ── Build one field per status group that has products ────────────────
        total_products = len(products)
        sections_built = 0

        for st in STATUS_ORDER:
            items = grouped.get(st, [])
            if not items:
                continue

            emoji, label, _ = STATUS_MAP.get(st, ("⚪", "Unknown", 0))

            lines = []
            for info in items:
                name    = info.get("name", "Unknown")
                version = info.get("version", "")
                key_    = name.strip().lower()
                entry   = last_upd.get(key_)

                # Version tag
                ver_str = f" `v{version}`" if version else ""

                # Last updated — relative timestamp or fallback
                if entry and entry.get("unix"):
                    upd_type = entry.get("update_type", "")
                    type_tag = f" `{upd_type}`" if upd_type else ""
                    lu_str   = f"<t:{entry['unix']}:R>{type_tag}"
                else:
                    lu_str = "No updates yet"

                lines.append(f"**{name}**{ver_str}  ·  {lu_str}")

            field_name  = f"{emoji}  {label}  ({len(items)})"
            field_value = "\n".join(lines)

            emb.add_field(name=field_name, value=field_value, inline=False)
            sections_built += 1

        # ── Status key as a clean footer block ────────────────────────────────
        key_parts = "  │  ".join(
            f"{e} {k.title()}" for k, (e, _, __) in STATUS_MAP.items()
        )
        emb.add_field(
            name  = "​",  # zero-width space — renders as a blank divider
            value = f"-# {key_parts}",
            inline= False,
        )

        # ── Footer ────────────────────────────────────────────────────────────
        meta  = data.get("meta", {})
        lu_by = meta.get("last_updated_by")
        lu_at = meta.get("last_updated_at")
        footer_text = (
            f"Last updated by {lu_by}  •  {pretty_dt(lu_at)}  •  {total_products} product(s)"
            if lu_by and lu_at
            else f"MangoMods  •  {total_products} product(s)  •  Live Status"
        )
        emb.set_footer(text=footer_text)

        return emb

    # ── Panel refresh ─────────────────────────────────────────────────────────

    async def refresh_panel(self) -> None:
        panels     = await self.panels.read()
        panel      = panels.get("status_panel")
        channel_id = self.bot.config.status_channel_id

        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        except Exception:
            return

        if not isinstance(channel, discord.TextChannel):
            return

        emb = await self._build_embed()

        if panel:
            try:
                msg = await channel.fetch_message(int(panel["message_id"]))
                await msg.edit(embed=emb)
                return
            except Exception:
                pass  # message gone — re-post below

        msg = await channel.send(embed=emb)
        panels["status_panel"] = {"channel_id": channel.id, "message_id": msg.id}
        await self.panels.write(panels)

    # ── /status panel ─────────────────────────────────────────────────────────

    @app_commands.command(name="panel", description="Post or refresh the product status panel.")
    async def panel(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.refresh_panel()
        await log_action(self.bot, "Status Panel Refreshed", f"By {interaction.user.mention}")
        await interaction.followup.send("✅ Status panel posted/refreshed.", ephemeral=True)


# ──────────────────────────────────────────────────────────────────────────────
# StatusCommands  (flat commands — /addproduct, /removeproduct, /updatestatus, /productstats)
# ──────────────────────────────────────────────────────────────────────────────

class StatusCommands(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot      = bot
        self.products = JSONStore("/data/products.json", {
            "products": {},
            "meta":     {"last_updated_by": None, "last_updated_at": None},
        })
        self.history  = JSONStore("/data/status_history.json", {"history": []})

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id}
                   for r in member.roles)

    def _key(self, name: str) -> str:
        return name.strip().lower()

    async def _touch_meta(self, staff: discord.Member) -> None:
        data = await self.products.read()
        data.setdefault("meta", {})
        data["meta"]["last_updated_by"] = staff.display_name
        data["meta"]["last_updated_at"] = iso_now()
        await self.products.write(data)

    async def _refresh_panel(self) -> None:
        cog = self.bot.get_cog("status")
        if cog and hasattr(cog, "refresh_panel"):
            await cog.refresh_panel()

    async def _record_history(
        self,
        product_name: str,
        old_status: Optional[str],
        new_status: str,
        staff: discord.Member,
    ) -> None:
        data = await self.history.read()
        data.setdefault("history", []).append({
            "product":    product_name,
            "old_status": old_status,
            "new_status": new_status,
            "changed_by": staff.display_name,
            "changed_by_id": staff.id,
            "timestamp":  iso_now(),
            "unix":       int(datetime.now(timezone.utc).timestamp()),
        })
        # Keep last 500 entries max
        data["history"] = data["history"][-500:]
        await self.history.write(data)

    async def _notify_status_change(
        self,
        guild: discord.Guild,
        product_info: dict,
        old_status: str,
        new_status: str,
        staff: discord.Member,
    ) -> None:
        """
        If a product transitions to 'detected' or back to 'undetected',
        ping the product's buyer role in the status channel.
        """
        notify_statuses = {"detected", "undetected", "risk"}
        if new_status not in notify_statuses:
            return

        buyer_role_id = product_info.get("buyer_role_id")
        if not buyer_role_id:
            return

        role = guild.get_role(int(buyer_role_id))
        if not role:
            return

        channel_id = self.bot.config.status_channel_id
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        except Exception:
            return
        if not isinstance(channel, discord.TextChannel):
            return

        name       = product_info.get("name", "Unknown Product")
        emoji      = _status_emoji(new_status)
        label      = _status_label(new_status)
        color      = _status_color(new_status)
        old_emoji  = _status_emoji(old_status)
        old_label  = _status_label(old_status)

        emb = discord.Embed(
            title=f"{emoji}  Status Change — {name}",
            colour=discord.Colour(color),
            timestamp=datetime.now(timezone.utc),
        )
        emb.add_field(name="Previous", value=f"{old_emoji}  {old_label}", inline=True)
        emb.add_field(name="Now",      value=f"{emoji}  {label}",         inline=True)
        emb.add_field(name="Updated by", value=staff.mention,             inline=True)

        if new_status == "detected":
            emb.add_field(
                name="⚠️  Action Required",
                value="**Stop using this product immediately.** Our team is working on an update.",
                inline=False,
            )
        elif new_status == "undetected":
            emb.add_field(
                name="✅  Safe to Use",
                value="This product has been updated and is safe to use again.",
                inline=False,
            )

        emb.set_footer(text="MangoMods  •  Status Notification")

        try:
            await channel.send(
                content=role.mention,
                embed=emb,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except Exception:
            pass

    # ── Autocomplete helpers ──────────────────────────────────────────────────

    async def _product_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        data     = await self.products.read()
        products = data.get("products", {})
        names    = [info.get("name", k) for k, info in products.items()]
        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()
        ][:25]

    async def _status_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=k.title(), value=k)
            for k in STATUS_MAP if current.lower() in k.lower()
        ]

    # ── /addproduct ───────────────────────────────────────────────────────────

    @app_commands.command(name="addproduct", description="Add a product to the status board. Staff only.")
    @app_commands.describe(
        name="Product display name",
        status="Initial status",
        version="Version number (e.g. 2.4.1)",
        buyer_role="Role to ping when status changes",
    )
    @app_commands.autocomplete(status=_status_autocomplete)
    async def addproduct(
        self,
        interaction: discord.Interaction,
        name: str,
        status: str,
        version: Optional[str] = None,
        buyer_role: Optional[discord.Role] = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        st = normalize_status(status)
        if st not in STATUS_MAP:
            return await interaction.response.send_message(
                f"Invalid status. Use: {', '.join(STATUS_MAP.keys())}.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        data = await self.products.read()
        data.setdefault("products", {})
        key = self._key(name)

        if key in data["products"]:
            return await interaction.followup.send(
                "That product already exists. Use `/updatestatus` to change its status.", ephemeral=True
            )

        entry: dict = {"name": name.strip(), "status": st}
        if version:
            entry["version"] = version.strip().lstrip("v")
        if buyer_role:
            entry["buyer_role_id"] = buyer_role.id

        data["products"][key] = entry
        data.setdefault("meta", {})
        data["meta"]["last_updated_by"] = interaction.user.display_name
        data["meta"]["last_updated_at"] = iso_now()
        await self.products.write(data)

        await self._record_history(name.strip(), None, st, interaction.user)
        await self._refresh_panel()
        await log_action(
            self.bot, "Product Added",
            f"By {interaction.user.mention}\n"
            f"**{name.strip()}** | Status: **{st}** | Version: **{version or 'N/A'}**"
            + (f" | Buyer role: {buyer_role.mention}" if buyer_role else ""),
        )
        await interaction.followup.send(
            f"✅ **{name.strip()}** added to the status board.", ephemeral=True
        )

    # ── /removeproduct ────────────────────────────────────────────────────────

    @app_commands.command(name="removeproduct", description="Remove a product from the status board. Staff only.")
    @app_commands.describe(name="Product to remove")
    @app_commands.autocomplete(name=_product_autocomplete)
    async def removeproduct(
        self,
        interaction: discord.Interaction,
        name: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        data = await self.products.read()
        key  = self._key(name)

        if key not in data.get("products", {}):
            return await interaction.followup.send("Product not found.", ephemeral=True)

        removed = data["products"].pop(key)
        data.setdefault("meta", {})
        data["meta"]["last_updated_by"] = interaction.user.display_name
        data["meta"]["last_updated_at"] = iso_now()
        await self.products.write(data)

        await self._refresh_panel()
        await log_action(
            self.bot, "Product Removed",
            f"By {interaction.user.mention}\nRemoved **{removed.get('name', name)}**",
        )
        await interaction.followup.send(
            f"✅ **{removed.get('name', name)}** removed from the status board.", ephemeral=True
        )

    # ── /updatestatus ─────────────────────────────────────────────────────────

    @app_commands.command(name="updatestatus", description="Update a product's status. Staff only.")
    @app_commands.describe(
        product="Product to update",
        status="New status",
        version="Update version number at the same time (optional)",
    )
    @app_commands.autocomplete(product=_product_autocomplete, status=_status_autocomplete)
    async def updatestatus(
        self,
        interaction: discord.Interaction,
        product: str,
        status: str,
        version: Optional[str] = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        st = normalize_status(status)
        if st not in STATUS_MAP:
            return await interaction.response.send_message(
                f"Invalid status. Use: {', '.join(STATUS_MAP.keys())}.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        data = await self.products.read()
        key  = self._key(product)

        if key not in data.get("products", {}):
            return await interaction.followup.send("Product not found.", ephemeral=True)

        old_status = data["products"][key].get("status", "testing")
        data["products"][key]["status"] = st

        if version:
            data["products"][key]["version"] = version.strip().lstrip("v")

        data.setdefault("meta", {})
        data["meta"]["last_updated_by"] = interaction.user.display_name
        data["meta"]["last_updated_at"] = iso_now()
        await self.products.write(data)

        product_info = data["products"][key]

        await self._record_history(product_info.get("name", product), old_status, st, interaction.user)

        # Notify buyer role on significant status changes
        if old_status != st:
            await self._notify_status_change(
                interaction.guild, product_info, old_status, st, interaction.user
            )

        await self._refresh_panel()
        await log_action(
            self.bot, "Status Updated",
            f"By {interaction.user.mention}\n"
            f"**{product_info.get('name', product)}**: **{old_status}** → **{st}**"
            + (f" | Version: **{version}**" if version else ""),
        )

        ver_note = f" | Version updated to `v{version.strip().lstrip('v')}`" if version else ""
        await interaction.followup.send(
            f"✅ **{product_info.get('name', product)}** → **{st}**{ver_note}\nPanel refreshed.",
            ephemeral=True,
        )

    # ── /updateversion ────────────────────────────────────────────────────────

    @app_commands.command(name="updateversion", description="Update a product's version number. Staff only.")
    @app_commands.describe(product="Product to update", version="New version (e.g. 2.4.1)")
    @app_commands.autocomplete(product=_product_autocomplete)
    async def updateversion(
        self,
        interaction: discord.Interaction,
        product: str,
        version: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        data = await self.products.read()
        key  = self._key(product)

        if key not in data.get("products", {}):
            return await interaction.followup.send("Product not found.", ephemeral=True)

        clean_ver = version.strip().lstrip("v")
        data["products"][key]["version"] = clean_ver
        data.setdefault("meta", {})
        data["meta"]["last_updated_by"] = interaction.user.display_name
        data["meta"]["last_updated_at"] = iso_now()
        await self.products.write(data)

        await self._refresh_panel()
        name = data["products"][key].get("name", product)
        await log_action(
            self.bot, "Version Updated",
            f"By {interaction.user.mention}\n**{name}** → `v{clean_ver}`",
        )
        await interaction.followup.send(
            f"✅ **{name}** version updated to `v{clean_ver}`.", ephemeral=True
        )

    # ── /productstats ─────────────────────────────────────────────────────────

    @app_commands.command(name="productstats", description="Overview of products by status. Staff only.")
    async def productstats(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        data     = await self.products.read()
        products = data.get("products", {})
        history  = (await self.history.read()).get("history", [])

        if not products:
            return await interaction.followup.send("No products on the board yet.", ephemeral=True)

        # Count by status
        counts: dict[str, list[str]] = {k: [] for k in STATUS_MAP}
        for info in products.values():
            st = info.get("status", "testing")
            counts.setdefault(st, []).append(info.get("name", "Unknown"))

        emb = discord.Embed(
            title="📊  Product Stats",
            colour=discord.Colour(0xF9A826),
            timestamp=datetime.now(timezone.utc),
        )

        total = len(products)
        emb.add_field(name="Total Products", value=str(total), inline=True)
        emb.add_field(name="\u200b", value="\u200b", inline=True)
        emb.add_field(name="\u200b", value="\u200b", inline=True)

        for st, (emoji, label, _) in STATUS_MAP.items():
            names = counts.get(st, [])
            value = "\n".join(f"• {n}" for n in names) if names else "*None*"
            emb.add_field(
                name=f"{emoji}  {label.split(' —')[0]} ({len(names)})",
                value=value,
                inline=True,
            )

        # Recent history — last 5 changes
        if history:
            recent = history[-5:][::-1]
            lines  = []
            for h in recent:
                old_e  = _status_emoji(h.get("old_status") or "")
                new_e  = _status_emoji(h.get("new_status", ""))
                ts_str = f"<t:{h['unix']}:R>" if h.get("unix") else ""
                lines.append(
                    f"{old_e}→{new_e} **{h['product']}** — by {h['changed_by']} {ts_str}"
                )
            emb.add_field(
                name="━━━━━━━━━━━━━━━━━━━━━━━━\nRecent Changes",
                value="\n".join(lines),
                inline=False,
            )

        emb.set_footer(text=f"MangoMods  •  {total} product(s) tracked")
        await interaction.followup.send(embed=emb, ephemeral=True)

    # ── /statushistory ────────────────────────────────────────────────────────

    @app_commands.command(name="statushistory", description="View status change history for a product. Staff only.")
    @app_commands.describe(product="Product to view history for")
    @app_commands.autocomplete(product=_product_autocomplete)
    async def statushistory(
        self,
        interaction: discord.Interaction,
        product: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not await self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        all_history = (await self.history.read()).get("history", [])
        key         = self._key(product)

        entries = [
            h for h in all_history
            if self._key(h.get("product", "")) == key
        ]

        if not entries:
            return await interaction.followup.send(
                f"No status history found for **{product}**.", ephemeral=True
            )

        emb = discord.Embed(
            title=f"📋  Status History — {product}",
            colour=discord.Colour(0x5865F2),
            timestamp=datetime.now(timezone.utc),
        )

        # Show up to 15 most recent, newest first
        display = entries[-15:][::-1]
        lines   = []
        for h in display:
            old_e  = _status_emoji(h.get("old_status") or "")
            new_e  = _status_emoji(h.get("new_status", ""))
            old_l  = (h.get("old_status") or "new").title()
            new_l  = h.get("new_status", "").title()
            ts_str = f"<t:{h['unix']}:R>" if h.get("unix") else ""
            lines.append(f"{old_e} **{old_l}** → {new_e} **{new_l}** — {h['changed_by']} {ts_str}")

        emb.description = "\n".join(lines)
        if len(entries) > 15:
            emb.set_footer(text=f"Showing most recent 15 of {len(entries)} entries")
        else:
            emb.set_footer(text=f"{len(entries)} change(s) on record")

        await interaction.followup.send(embed=emb, ephemeral=True)


# ──────────────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatusPanel(bot))
    await bot.add_cog(StatusCommands(bot))
