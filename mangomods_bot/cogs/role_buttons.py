from __future__ import annotations

from typing import Optional

"""
cogs/role_buttons.py
────────────────────
Self-assign role button panels. Members click a button to get/remove a role.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO CONFIGURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Everything is defined in ROLE_PANELS below. You never need to touch anything
outside of that dict. Here's the full structure with every available option:

ROLE_PANELS = {

    "panel_key": {                      # Internal ID — no spaces, lowercase.
                                        # Used in /rolebuttons post <panel_key>

        "title":       "Panel Title",   # Shown as the embed title.

        "description": "Some text",     # Shown as the embed description.
                                        # Supports Discord markdown.
                                        # Set to None to omit.

        "color":       "brand",         # Embed colour. Options:
                                        #   "brand"   — mango gold (default)
                                        #   "success" — green
                                        #   "info"    — blurple
                                        #   "warning" — amber
                                        #   "muted"   — grey
                                        #   "premium" — bright gold
                                        # Or pass a hex int: 0xFF5733

        "footer":      "Roles",         # Footer suffix. Shows as:
                                        #   "MangoMods  •  Roles"

        "thumbnail":   None,            # URL string or None.
                                        # Shown top-right of the embed.

        "roles": [                      # List of button definitions.
            {
                "role_id":  123456789,  # REQUIRED. The Discord role ID to assign.
                                        # Right-click a role → Copy ID.

                "label":    "Updates",  # REQUIRED. Text shown on the button.

                "emoji":    "🔔",       # Optional. Emoji shown before the label.
                                        # Can be a unicode emoji or a custom emoji
                                        # string like "<:mango:123456789>".
                                        # Set to None to omit.

                "style":    "primary",  # Button colour. Options:
                                        #   "primary"   — blurple
                                        #   "secondary" — grey
                                        #   "success"   — green
                                        #   "danger"    — red
                                        # Default: "primary"

                "description": "Ping me for product updates.",
                                        # Optional. Shown in the embed field
                                        # below the panel description.
                                        # Set to None to omit from the field list.

                "exclusive_group": None,
                                        # Optional string. If two or more roles
                                        # share the same exclusive_group string,
                                        # assigning one will remove the others
                                        # in that group. Use this for mutually
                                        # exclusive options like game regions.
                                        # Set to None for independent toggle.
            },
        ],

        "max_roles": None,              # Optional int. If set, limits how many
                                        # roles from this panel a member can hold
                                        # at once. None = unlimited.

        "required_role_id": None,       # Optional role ID. If set, only members
                                        # with this role can interact with buttons
                                        # on this panel. None = anyone.

        "removable": True,              # If True (default), clicking a role the
                                        # member already has will REMOVE it.
                                        # If False, clicking again does nothing
                                        # (assign-only mode).
    },

}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE PANELS (replace role IDs with your real ones)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

ROLE_PANELS: dict[str, dict] = {

    # ── Notification roles ────────────────────────────────────────────────────
    "notifications": {
        "title":       "🔔  Notification Roles",
        "description": (
            "Pick which pings you want to receive.\n"
            "Click a button to add or remove the role."
        ),
        "color":       "brand",
        "footer":      "Notification Roles",
        "thumbnail":   None,
        "max_roles":   None,
        "required_role_id": None,
        "removable":   True,
        "roles": [
            {
                "role_id":      1519881584017408020,   # ← REPLACE with your Update Pings role ID
                "label":        "Update Pings",
                "emoji":        "🔔",
                "style":        "primary",
                "description":  "Get pinged when a cheat is updated.",
                "exclusive_group": None,
            },
            {
                "role_id":      1519881885474361414,   # ← REPLACE with your Giveaway Pings role ID
                "label":        "Giveaway Pings",
                "emoji":        "🎁",
                "style":        "success",
                "description":  "Get pinged for giveaways and events.",
                "exclusive_group": None,
            },
            {
                "role_id":      1519882194393370674,   # ← REPLACE with your Status Alerts role ID
                "label":        "Status Alerts",
                "emoji":        "⚠️",
                "style":        "danger",
                "description":  "Get pinged when a product goes detected.",
                "exclusive_group": None,
            },
            {
                "role_id":      1519882359783166172,   # ← REPLACE with your Promo Alerts role ID
                "label":        "Promo Alerts",
                "emoji":        "💸",
                "style":        "secondary",
                "description":  "Get pinged for discount codes and promos.",
                "exclusive_group": None,
            },
        ],
    },

    # ── Game roles (mutually exclusive example) ───────────────────────────────
    "games": {
        "title":       "🎮  Game Roles",
        "description": (
            "Pick your main game. You can only hold **one** at a time.\n"
            "Switching will remove your previous selection."
        ),
        "color":       "info",
        "footer":      "Game Roles",
        "thumbnail":   None,
        "max_roles":   1,
        "required_role_id": None,
        "removable":   True,
        "roles": [
            {
                "role_id":      1460000178873438218,   # ← REPLACE with your CODM role ID
                "label":        "AegisGC3 CODM GL",
                "emoji":        "🔫",
                "style":        "primary",
                "description":  "Call of Duty Mobile Global.",
                "exclusive_group": "game",
            },
            {
                "role_id":      1460000178873438218,   # ← REPLACE with your CODM role ID
                "label":        "AegisGC3 CODM GR",
                "emoji":        "🔫",
                "style":        "primary",
                "description":  "Call of Duty Mobile Garena.",
                "exclusive_group": "game",
            },
            {
                "role_id":      1439891277230637147,   # ← REPLACE with your Free Fire role ID
                "label":        "Fluorite Free Fire",
                "emoji":        "🔥",
                "style":        "primary",
                "description":  "Garena Free Fire.",
                "exclusive_group": "game",
            },
            {
                "role_id":      1439891277230637147,   # ← REPLACE with your Free Fire role ID
                "label":        "Fluorite Mobile Legends",
                "emoji":        "🔥",
                "style":        "primary",
                "description":  "Mobile Legends Bang Bang.",
                "exclusive_group": "game",
            },
        ],
    },

}

# ─────────────────────────────────────────────────────────────────────────────
# Nothing below this line needs to be edited.
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed, context_color, COLORS
from mangomods_bot.utils.log import log_action


_BUTTON_STYLES: dict[str, discord.ButtonStyle] = {
    "primary":   discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success":   discord.ButtonStyle.success,
    "danger":    discord.ButtonStyle.danger,
}


def _resolve_color(color) -> discord.Colour:
    if isinstance(color, int):
        return discord.Colour(color)
    if isinstance(color, str):
        return discord.Colour(COLORS.get(color, COLORS["brand"]))
    return discord.Colour(COLORS["brand"])


# ──────────────────────────────────────────────────────────────────────────────
# Dynamic persistent button
# ──────────────────────────────────────────────────────────────────────────────

class RoleButton(discord.ui.Button):
    """
    One button per role. custom_id encodes panel_key and role_id so it
    survives restarts with no state lookup.

    Format: mangomods:rolebutton:<panel_key>:<role_id>
    """

    def __init__(self, panel_key: str, role_cfg: dict):
        role_id = role_cfg["role_id"]
        style   = _BUTTON_STYLES.get(role_cfg.get("style", "primary"), discord.ButtonStyle.primary)
        emoji   = role_cfg.get("emoji") or None

        super().__init__(
            label     = role_cfg["label"],
            style     = style,
            emoji     = emoji,
            custom_id = f"mangomods:rolebutton:{panel_key}:{role_id}",
        )
        self.panel_key = panel_key
        self.role_cfg  = role_cfg
        self.role_id   = role_id

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("RoleButtons")
        if not cog:
            return await interaction.response.send_message(
                "Role button system not loaded.", ephemeral=True
            )
        await cog.handle_role_toggle(interaction, self.panel_key, self.role_cfg)


class RolePanelView(discord.ui.View):
    """
    Persistent view for a single panel. Builds one RoleButton per role config.
    """

    def __init__(self, panel_key: str, panel_cfg: dict):
        super().__init__(timeout=None)
        for role_cfg in panel_cfg.get("roles", []):
            self.add_item(RoleButton(panel_key, role_cfg))


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────

class RoleButtons(commands.Cog):
    """
    /rolebuttons post   <panel_key>  [channel]  — post a panel
    /rolebuttons repost <panel_key>             — edit existing panel in-place
    /rolebuttons list                           — list all configured panels
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot   = bot
        self.store = JSONStore("/data/role_panels.json", {"panels": {}})
        # panels schema: { panel_key: { "channel_id": int, "message_id": int } }

    async def cog_load(self) -> None:
        # Register all persistent views so buttons work after a restart
        for panel_key, panel_cfg in ROLE_PANELS.items():
            self.bot.add_view(RolePanelView(panel_key, panel_cfg))

    def _is_staff(self, member: discord.Member) -> bool:
        return any(
            r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id}
            for r in member.roles
        )

    # ── Embed builder ─────────────────────────────────────────────────────────

    def _build_panel_embed(self, panel_key: str) -> discord.Embed:
        cfg   = ROLE_PANELS[panel_key]
        color = _resolve_color(cfg.get("color", "brand"))

        emb = discord.Embed(
            title       = cfg.get("title") or "Role Selection",
            description = cfg.get("description") or None,
            colour      = color,
            timestamp   = datetime.now(timezone.utc),
        )

        # Footer
        import os
        brand = os.getenv("BRAND_NAME", "MangoMods")
        footer_suffix = cfg.get("footer", "Roles")
        from mangomods_bot.utils.embeds import _logo_url
        logo = _logo_url()
        emb.set_footer(
            text     = f"{brand}  •  {footer_suffix}",
            icon_url = logo or None,
        )

        # Thumbnail
        if cfg.get("thumbnail"):
            emb.set_thumbnail(url=cfg["thumbnail"])

        # Role list fields — one per role that has a description
        described_roles = [r for r in cfg.get("roles", []) if r.get("description")]
        if described_roles:
            lines = []
            for r in described_roles:
                emoji   = r.get("emoji", "")
                emoji_s = f"{emoji} " if emoji else ""
                role_mention = f"<@&{r['role_id']}>"
                lines.append(f"{emoji_s}**{r['label']}** — {r['description']} ({role_mention})")
            emb.add_field(name="Available Roles", value="\n".join(lines), inline=False)

        # Constraints hint
        hints = []
        max_roles = cfg.get("max_roles")
        if max_roles:
            hints.append(f"Maximum **{max_roles}** role(s) from this panel at once.")
        req_role_id = cfg.get("required_role_id")
        if req_role_id:
            hints.append(f"Requires <@&{req_role_id}> to interact.")
        if not cfg.get("removable", True):
            hints.append("Roles assigned here cannot be removed by clicking again.")
        if hints:
            emb.add_field(name="ℹ️  Rules", value="\n".join(f"• {h}" for h in hints), inline=False)

        return emb

    # ── Core toggle logic ─────────────────────────────────────────────────────

    async def handle_role_toggle(
        self,
        interaction: discord.Interaction,
        panel_key: str,
        role_cfg: dict,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use this in a server.", ephemeral=True
            )

        panel_cfg = ROLE_PANELS.get(panel_key)
        if not panel_cfg:
            return await interaction.response.send_message(
                "This panel is no longer configured.", ephemeral=True
            )

        member = interaction.user
        guild  = interaction.guild

        # Required role gate
        req_role_id = panel_cfg.get("required_role_id")
        if req_role_id:
            if not any(r.id == req_role_id for r in member.roles):
                role = guild.get_role(req_role_id)
                name = role.mention if role else f"<@&{req_role_id}>"
                return await interaction.response.send_message(
                    f"You need {name} to use these buttons.", ephemeral=True
                )

        target_role = guild.get_role(role_cfg["role_id"])
        if not target_role:
            return await interaction.response.send_message(
                f"Role not found — it may have been deleted. (ID: {role_cfg['role_id']})",
                ephemeral=True,
            )

        removable        = panel_cfg.get("removable", True)
        max_roles        = panel_cfg.get("max_roles")
        exclusive_group  = role_cfg.get("exclusive_group")
        has_role         = target_role in member.roles

        # ── Remove (toggle off) ───────────────────────────────────────────────
        if has_role:
            if not removable:
                return await interaction.response.send_message(
                    f"You already have **{target_role.name}** and it cannot be removed from here.",
                    ephemeral=True,
                )
            try:
                await member.remove_roles(target_role, reason=f"Role button — {panel_key}")
            except discord.Forbidden:
                return await interaction.response.send_message(
                    "I don't have permission to remove that role.", ephemeral=True
                )
            return await interaction.response.send_message(
                f"✅ Removed **{target_role.name}**.", ephemeral=True
            )

        # ── Assign ────────────────────────────────────────────────────────────

        # Max roles check
        if max_roles is not None:
            panel_role_ids = {r["role_id"] for r in panel_cfg.get("roles", [])}
            current_panel_roles = [r for r in member.roles if r.id in panel_role_ids]
            if len(current_panel_roles) >= max_roles:
                return await interaction.response.send_message(
                    f"You can only hold **{max_roles}** role(s) from this panel at once.\n"
                    "Remove one first by clicking its button again.",
                    ephemeral=True,
                )

        # Exclusive group — remove all other roles in the same group first
        roles_to_remove: list[discord.Role] = []
        if exclusive_group:
            for other_cfg in panel_cfg.get("roles", []):
                if (
                    other_cfg.get("exclusive_group") == exclusive_group
                    and other_cfg["role_id"] != role_cfg["role_id"]
                ):
                    other_role = guild.get_role(other_cfg["role_id"])
                    if other_role and other_role in member.roles:
                        roles_to_remove.append(other_role)

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Role button exclusive group — {panel_key}")
            await member.add_roles(target_role, reason=f"Role button — {panel_key}")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "I don't have permission to assign that role.", ephemeral=True
            )
        except Exception:
            return await interaction.response.send_message(
                "Something went wrong assigning the role.", ephemeral=True
            )

        msg = f"✅ You now have **{target_role.name}**."
        if roles_to_remove:
            removed_names = ", ".join(f"**{r.name}**" for r in roles_to_remove)
            msg += f"\nRemoved: {removed_names} (exclusive group)."

        await interaction.response.send_message(msg, ephemeral=True)

    # ── Commands ──────────────────────────────────────────────────────────────

    group = app_commands.Group(name="rolebuttons", description="Role button panel commands.")

    @group.command(name="post", description="Post a role button panel. Staff only.")
    @app_commands.describe(
        panel_key = "Which panel to post (defined in role_buttons.py)",
        channel   = "Channel to post in (defaults to current channel)",
    )
    async def post(
        self,
        interaction: discord.Interaction,
        panel_key: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)
        if panel_key not in ROLE_PANELS:
            keys = ", ".join(f"`{k}`" for k in ROLE_PANELS)
            return await interaction.response.send_message(
                f"Panel `{panel_key}` not found. Available: {keys}", ephemeral=True
            )

        target_ch = channel or interaction.channel
        if not isinstance(target_ch, discord.TextChannel):
            return await interaction.response.send_message(
                "Target must be a text channel.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        emb  = self._build_panel_embed(panel_key)
        view = RolePanelView(panel_key, ROLE_PANELS[panel_key])
        msg  = await target_ch.send(embed=emb, view=view)

        # Persist message reference
        data = await self.store.read()
        data.setdefault("panels", {})[panel_key] = {
            "channel_id": target_ch.id,
            "message_id": msg.id,
        }
        await self.store.write(data)

        await log_action(
            self.bot,
            "Role Panel Posted",
            f"By {interaction.user.mention}\nPanel: `{panel_key}` in {target_ch.mention}",
        )
        await interaction.followup.send(
            f"✅ Panel `{panel_key}` posted in {target_ch.mention}.", ephemeral=True
        )

    @group.command(name="repost", description="Edit an existing role panel in-place. Staff only.")
    @app_commands.describe(panel_key="Which panel to refresh")
    async def repost(
        self,
        interaction: discord.Interaction,
        panel_key: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)
        if panel_key not in ROLE_PANELS:
            keys = ", ".join(f"`{k}`" for k in ROLE_PANELS)
            return await interaction.response.send_message(
                f"Panel `{panel_key}` not found. Available: {keys}", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        data  = await self.store.read()
        saved = data.get("panels", {}).get(panel_key)

        if not saved:
            return await interaction.followup.send(
                f"No posted message found for `{panel_key}`. Use `/rolebuttons post` first.",
                ephemeral=True,
            )

        try:
            ch  = interaction.guild.get_channel(saved["channel_id"])
            msg = await ch.fetch_message(saved["message_id"])
            emb  = self._build_panel_embed(panel_key)
            view = RolePanelView(panel_key, ROLE_PANELS[panel_key])
            await msg.edit(embed=emb, view=view)
        except discord.NotFound:
            return await interaction.followup.send(
                "Original message not found — use `/rolebuttons post` to re-post it.",
                ephemeral=True,
            )
        except Exception as e:
            return await interaction.followup.send(f"Failed to edit message: {e}", ephemeral=True)

        await log_action(
            self.bot,
            "Role Panel Refreshed",
            f"By {interaction.user.mention}\nPanel: `{panel_key}`",
        )
        await interaction.followup.send(
            f"✅ Panel `{panel_key}` refreshed in-place.", ephemeral=True
        )

    @group.command(name="list", description="List all configured role panels.")
    async def list_panels(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        data   = await self.store.read()
        posted = data.get("panels", {})

        emb = mango_embed(
            self.bot,
            title  = "📋  Role Button Panels",
            color  = "info",
            footer = "Role Buttons",
        )

        for key, cfg in ROLE_PANELS.items():
            p     = posted.get(key)
            loc   = f"<#{p['channel_id']}> ([jump](https://discord.com/channels/{interaction.guild.id}/{p['channel_id']}/{p['message_id']}))" if p else "*Not posted*"
            roles = ", ".join(r["label"] for r in cfg.get("roles", []))
            emb.add_field(
                name  = f"`{key}` — {cfg.get('title', key)}",
                value = f"Roles: {roles}\nPosted: {loc}",
                inline= False,
            )

        await interaction.followup.send(embed=emb, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleButtons(bot))
