from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.storage import JSONStore


class UserInfo(commands.Cog):
    """
    /userinfo  — detailed member overview (join date, roles, warnings, open ticket)
    /cases     — full mod case history pulled from warnings + mod_cases
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot        = bot
        self.warn_store = JSONStore("/data/warnings.json",  {"warnings": {}})
        self.case_store = JSONStore("/data/mod_cases.json", {"next_case": 1})

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(
            r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id}
            for r in member.roles
        )

    async def _ephemeral(self, interaction: discord.Interaction, content: str) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)
        except Exception:
            pass

    # ── /userinfo ─────────────────────────────────────────────────────────────

    @app_commands.command(name="userinfo", description="View detailed info about a member. Staff only.")
    @app_commands.describe(member="Member to look up (defaults to yourself)")
    async def userinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")

        # Non-staff can only look up themselves
        target = member or interaction.user
        if target.id != interaction.user.id and not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild

        # Warnings
        warn_data = await self.warn_store.read()
        key       = f"{guild.id}:{target.id}"
        warnings  = warn_data.get("warnings", {}).get(key, [])
        warn_count = len(warnings)

        # Open ticket check
        from mangomods_bot.storage import JSONStore as _JS
        ticket_store = _JS("/data/tickets.json", {"open_tickets_by_user": {}})
        ticket_data  = await ticket_store.read()
        open_ticket  = ticket_data.get("open_tickets_by_user", {}).get(str(target.id))

        # Role list (exclude @everyone, cap at 20)
        roles = [r for r in reversed(target.roles) if r.id != guild.id]
        role_str = " ".join(r.mention for r in roles[:20])
        if len(roles) > 20:
            role_str += f" *+{len(roles) - 20} more*"
        if not role_str:
            role_str = "None"

        # Timestamps
        created_ts = int(target.created_at.timestamp())
        joined_ts  = int(target.joined_at.timestamp()) if target.joined_at else None

        # Account age warning
        age_days = (datetime.now(timezone.utc) - target.created_at).days
        age_flag = " ⚠️ *New account*" if age_days < 7 else ""

        # Status / activity
        status_map = {
            discord.Status.online:    "🟢 Online",
            discord.Status.idle:      "🌙 Idle",
            discord.Status.dnd:       "⛔ Do Not Disturb",
            discord.Status.offline:   "⚫ Offline",
        }
        status_str = status_map.get(target.status, "⚫ Offline")

        # Build embed
        color = discord.Colour(0xED4245) if warn_count >= 3 else discord.Colour(0xF9A826)

        emb = discord.Embed(
            title=f"👤  {target.display_name}",
            colour=color,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_thumbnail(url=target.display_avatar.url)

        emb.add_field(name="Username",  value=str(target),        inline=True)
        emb.add_field(name="ID",        value=str(target.id),     inline=True)
        emb.add_field(name="Status",    value=status_str,         inline=True)

        emb.add_field(
            name="Account Created",
            value=f"<t:{created_ts}:F> (<t:{created_ts}:R>){age_flag}",
            inline=False,
        )

        if joined_ts:
            emb.add_field(
                name="Joined Server",
                value=f"<t:{joined_ts}:F> (<t:{joined_ts}:R>)",
                inline=False,
            )

        emb.add_field(
            name=f"Roles ({len(roles)})",
            value=role_str,
            inline=False,
        )

        # Mod info — staff only
        if await self._is_staff(interaction.user):
            warn_display = f"**{warn_count}**" if warn_count == 0 else f"⚠️ **{warn_count}**"
            emb.add_field(name="Warnings",    value=warn_display,    inline=True)
            emb.add_field(name="Bot Account", value="Yes" if target.bot else "No", inline=True)

            if open_ticket:
                ch_id   = open_ticket.get("channel_id")
                t_type  = open_ticket.get("type", "ticket").title()
                t_prio  = open_ticket.get("priority", "medium").title()
                emb.add_field(
                    name="Open Ticket",
                    value=f"<#{ch_id}> • {t_type} • {t_prio}",
                    inline=False,
                )
            else:
                emb.add_field(name="Open Ticket", value="None", inline=True)

        emb.set_footer(text=f"MangoMods  •  Requested by {interaction.user.display_name}")

        await interaction.followup.send(embed=emb, ephemeral=True)

    # ── /cases ────────────────────────────────────────────────────────────────

    @app_commands.command(name="cases", description="View mod case history for a member. Staff only.")
    @app_commands.describe(member="Member to look up")
    async def cases(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild

        # Pull warnings
        warn_data  = await self.warn_store.read()
        key        = f"{guild.id}:{member.id}"
        warnings   = warn_data.get("warnings", {}).get(key, [])

        # Action icons
        ACTION_ICONS: dict[str, str] = {
            "warn":                   "⚠️",
            "mute":                   "🔇",
            "mute (auto-escalation)": "🔇",
            "timeout":                "⏱️",
            "unmute":                 "🔊",
            "kick":                   "👢",
            "softban":                "🔨",
            "ban":                    "🔨",
            "ban (auto-escalation)":  "🔨",
            "clearwarns":             "✅",
        }

        emb = discord.Embed(
            title=f"📋  Case History — {member.display_name}",
            colour=discord.Colour(0x5865F2),
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_thumbnail(url=member.display_avatar.url)
        emb.add_field(name="User", value=member.mention, inline=True)
        emb.add_field(name="ID",   value=str(member.id), inline=True)
        emb.add_field(name="\u200b", value="\u200b",     inline=True)

        # Warnings section
        if warnings:
            # Show up to 5 most recent
            display = warnings[-5:]
            lines = []
            for i, w in enumerate(display, start=len(warnings) - len(display) + 1):
                try:
                    ts     = datetime.fromisoformat(w["timestamp"].replace("Z", "+00:00"))
                    ts_str = f"<t:{int(ts.timestamp())}:R>"
                except Exception:
                    ts_str = "Unknown"
                mod = w.get("moderator_name", "Unknown")
                lines.append(f"⚠️ **Warn #{i}** — {w['reason']} • by {mod} • {ts_str}")

            if len(warnings) > 5:
                lines.append(f"*…and {len(warnings) - 5} older warning(s). Use `/warnings` for full list.*")

            emb.add_field(
                name=f"Warnings ({len(warnings)} total)",
                value="\n".join(lines),
                inline=False,
            )
        else:
            emb.add_field(name="Warnings", value="None on record.", inline=False)

        # Mute / ban / kick history from mod_cases
        # We don't store per-user case records in the current schema —
        # cases are append-only in the log channel. So we surface what we have:
        # the warnings store covers warns; for mutes/bans we note the limitation.
        emb.add_field(
            name="ℹ️  Mutes / Bans / Kicks",
            value=(
                "Full action history is logged in the mod log channel.\n"
                "Use the log channel search or `/warnings` for warn-only records.\n"
                "*Tip: add per-user case indexing to `mod_cases.json` for full lookup.*"
            ),
            inline=False,
        )

        total_actions = len(warnings)
        emb.set_footer(text=f"MangoMods  •  {total_actions} warning(s) on record")

        await interaction.followup.send(embed=emb, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UserInfo(bot))
