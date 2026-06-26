from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.storage import JSONStore

# ── Re-use the duration parser and human formatter from mute.py ──────────────
import re

_DURATION_RE = re.compile(r"^\s*(\d+)\s*(s|m|h|d|w|mo|y)\s*$", re.IGNORECASE)
MAX_TIMEOUT = timedelta(days=28)

WARN_COLOR  = 0xF9A826   # mango gold
CLEAR_COLOR = 0x57F287   # green
INFO_COLOR  = 0x5865F2   # blurple


def parse_duration(text: str) -> Optional[timedelta]:
    m = _DURATION_RE.match(text or "")
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    if n <= 0:
        return None
    if unit == "s":   return timedelta(seconds=n)
    if unit == "m":   return timedelta(minutes=n)
    if unit == "h":   return timedelta(hours=n)
    if unit == "d":   return timedelta(days=n)
    if unit == "w":   return timedelta(weeks=n)
    if unit == "mo":  return timedelta(days=30 * n)
    if unit == "y":   return timedelta(days=365 * n)
    return None


def human_duration(td: timedelta) -> str:
    s = int(td.total_seconds())
    if s < 60:    return f"{s}s"
    m = s // 60
    if m < 60:    return f"{m}m"
    h = m // 60
    if h < 24:    return f"{h}h"
    return f"{h // 24}d"


# ── Escalation config ─────────────────────────────────────────────────────────
# Env vars: WARN_ESCALATE_<n>=<action>:<duration|blank>
#   e.g.  WARN_ESCALATE_3=mute:1h
#         WARN_ESCALATE_5=ban
#
# Supported actions: mute, ban
# Duration required for mute, ignored for ban.

def _parse_escalation_map() -> dict[int, dict[str, Any]]:
    """
    Reads WARN_ESCALATE_N env vars and returns:
      { warn_count: { "action": "mute"|"ban", "duration": timedelta|None } }
    """
    result: dict[int, dict[str, Any]] = {}
    for key, val in os.environ.items():
        if not key.startswith("WARN_ESCALATE_"):
            continue
        try:
            threshold = int(key[len("WARN_ESCALATE_"):])
        except ValueError:
            continue

        val = (val or "").strip().lower()
        if not val:
            continue

        parts = val.split(":", 1)
        action = parts[0].strip()
        if action not in {"mute", "ban"}:
            continue

        duration: Optional[timedelta] = None
        if len(parts) == 2 and parts[1].strip():
            duration = parse_duration(parts[1].strip())

        if action == "mute" and duration is None:
            continue  # mute without duration is invalid

        result[threshold] = {"action": action, "duration": duration}

    return result


# ── Cog ───────────────────────────────────────────────────────────────────────

class WarnCog(commands.Cog):
    """
    /warn        — issue a warning to a member (staff only)
    /warnings    — view all warnings for a member (staff only)
    /clearwarns  — clear all warnings for a member (staff only)

    Auto-escalation fires automatically on hitting a configured threshold.
    Configure via env:
      WARN_ESCALATE_3=mute:1h    -> on 3rd warning, mute for 1h
      WARN_ESCALATE_5=ban        -> on 5th warning, ban permanently
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store      = JSONStore("/data/warnings.json",  {"warnings": {}})
        self.case_store = JSONStore("/data/mod_cases.json", {"next_case": 1})
        self.escalation = _parse_escalation_map()

    # ── Permissions ───────────────────────────────────────────────────────────

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(
            r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id}
            for r in member.roles
        )

    def _muted_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        rid = getattr(self.bot.config, "muted_role_id", None)
        return guild.get_role(rid) if rid else None

    def _hierarchy_blocked(self, guild: discord.Guild, target: discord.Member) -> bool:
        me = guild.me
        return bool(me and target.top_role >= me.top_role)

    # ── Response helpers ──────────────────────────────────────────────────────

    async def _ephemeral(self, interaction: discord.Interaction, content: str) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)
        except Exception:
            pass

    # ── Case log (mirrors mute.py format exactly) ─────────────────────────────

    async def _next_case(self) -> int:
        data = await self.case_store.read()
        n = int(data.get("next_case", 1))
        data["next_case"] = n + 1
        await self.case_store.write(data)
        return n

    async def _send_case_log(
        self,
        *,
        action: str,
        color: int,
        moderator: discord.Member,
        offender: discord.Member | discord.User,
        reason: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        case_no = await self._next_case()

        emb = discord.Embed(
            title=f"{action} | case {case_no}",
            colour=discord.Colour(color),
            timestamp=datetime.now(timezone.utc),
        )
        emb.add_field(name="Offender",              value=f"{offender.mention} ({offender})",   inline=False)
        emb.add_field(name="Reason",                value=reason or "No reason given.",          inline=False)
        emb.add_field(name="Responsible moderator", value=f"{moderator.mention} ({moderator})", inline=False)
        emb.add_field(name="ID",                    value=str(offender.id),                     inline=False)

        if extra:
            for k, v in extra.items():
                emb.add_field(name=k, value=v, inline=False)

        emb.set_footer(text=f"Today • case {case_no}")

        try:
            ch = self.bot.get_channel(self.bot.config.log_channel_id) or \
                 await self.bot.fetch_channel(self.bot.config.log_channel_id)
            if isinstance(ch, discord.TextChannel):
                await ch.send(emb)
        except Exception:
            pass

    # ── Warning storage helpers ───────────────────────────────────────────────

    async def _get_warnings(self, guild_id: int, user_id: int) -> list[dict[str, Any]]:
        data = await self.store.read()
        key  = f"{guild_id}:{user_id}"
        return list(data.get("warnings", {}).get(key, []))

    async def _add_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        moderator_name: str,
        reason: str,
    ) -> list[dict[str, Any]]:
        data = await self.store.read()
        key  = f"{guild_id}:{user_id}"
        data.setdefault("warnings", {}).setdefault(key, [])
        data["warnings"][key].append({
            "reason":         reason,
            "moderator_id":   moderator_id,
            "moderator_name": moderator_name,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        })
        await self.store.write(data)
        return list(data["warnings"][key])

    async def _clear_warnings(self, guild_id: int, user_id: int) -> int:
        data = await self.store.read()
        key  = f"{guild_id}:{user_id}"
        removed = len(data.get("warnings", {}).get(key, []))
        data.setdefault("warnings", {})[key] = []
        await self.store.write(data)
        return removed

    # ── DM notifications ──────────────────────────────────────────────────────

    async def _dm_warned(
        self,
        member: discord.Member,
        reason: str,
        warn_count: int,
        guild_name: str,
    ) -> None:
        try:
            emb = discord.Embed(
                title="⚠️  You have been warned",
                colour=discord.Colour(WARN_COLOR),
                timestamp=datetime.now(timezone.utc),
            )
            emb.add_field(name="Server",         value=guild_name,      inline=True)
            emb.add_field(name="Total Warnings", value=str(warn_count), inline=True)
            emb.add_field(name="Reason",         value=reason,          inline=False)
            emb.set_footer(text="Continued violations may result in a mute or ban.")
            await member.send(embed=emb)
        except Exception:
            pass  # DMs disabled — fail silently

    async def _dm_escalated(
        self,
        member: discord.Member,
        action: str,
        reason: str,
        duration: Optional[timedelta],
        guild_name: str,
    ) -> None:
        try:
            action_str = f"muted for {human_duration(duration)}" if action == "mute" and duration else "banned"
            emb = discord.Embed(
                title=f"🔨  You have been {action_str}",
                colour=discord.Colour(0xED4245),
                timestamp=datetime.now(timezone.utc),
            )
            emb.add_field(name="Server", value=guild_name, inline=True)
            emb.add_field(name="Reason", value=reason,     inline=False)
            emb.set_footer(text="This action was triggered automatically due to repeated warnings.")
            await member.send(embed=emb)
        except Exception:
            pass

    # ── Auto-escalation ───────────────────────────────────────────────────────

    async def _maybe_escalate(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        warn_count: int,
        warn_reason: str,
    ) -> Optional[str]:
        """
        Check if warn_count hits a configured threshold.
        Fires the action and returns a status string, or None if no rule matched.
        """
        rule = self.escalation.get(warn_count)
        if not rule:
            return None

        action   = rule["action"]
        duration = rule.get("duration")
        guild    = interaction.guild
        reason   = f"Auto-escalation at {warn_count} warnings — {warn_reason}"

        if self._hierarchy_blocked(guild, member):
            return f"⚠️ Escalation would fire ({action}) but role hierarchy blocked it."

        # DM before the action — ban cuts off DM access
        await self._dm_escalated(member, action, reason, duration, guild.name)

        if action == "mute" and duration:
            apply_td = min(duration, MAX_TIMEOUT)
            try:
                await member.timeout(apply_td, reason=reason)
            except discord.Forbidden:
                return "⚠️ Escalation (mute) failed — missing permissions."
            except Exception:
                return "⚠️ Escalation (mute) failed — unexpected error."

            await self._send_case_log(
                action    = "mute (auto-escalation)",
                color     = WARN_COLOR,
                moderator = interaction.user,
                offender  = member,
                reason    = reason,
                extra     = {"Duration": human_duration(apply_td), "Trigger": f"{warn_count} warnings"},
            )
            return f"🔇 Auto-escalation fired: muted for **{human_duration(apply_td)}** ({warn_count} warnings)."

        if action == "ban":
            try:
                await guild.ban(member, reason=reason, delete_message_days=0)
            except discord.Forbidden:
                return "⚠️ Escalation (ban) failed — missing permissions."
            except Exception:
                return "⚠️ Escalation (ban) failed — unexpected error."

            await self._send_case_log(
                action    = "ban (auto-escalation)",
                color     = 0xED4245,
                moderator = interaction.user,
                offender  = member,
                reason    = reason,
                extra     = {"Trigger": f"{warn_count} warnings"},
            )
            return f"🔨 Auto-escalation fired: **banned** ({warn_count} warnings)."

        return None

    # ── Commands ──────────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Issue a warning to a member. Staff only.")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning")
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")
        if member.bot:
            return await self._ephemeral(interaction, "You can't warn a bot.")
        if member.id == interaction.user.id:
            return await self._ephemeral(interaction, "You can't warn yourself.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        pretty_reason = reason.strip() or "No reason given."

        warnings = await self._add_warning(
            guild_id       = interaction.guild.id,
            user_id        = member.id,
            moderator_id   = interaction.user.id,
            moderator_name = interaction.user.display_name,
            reason         = pretty_reason,
        )
        warn_count = len(warnings)

        await self._send_case_log(
            action    = "warn",
            color     = WARN_COLOR,
            moderator = interaction.user,
            offender  = member,
            reason    = pretty_reason,
            extra     = {"Warning #": str(warn_count)},
        )

        await self._dm_warned(member, pretty_reason, warn_count, interaction.guild.name)

        escalation_msg = await self._maybe_escalate(
            interaction, member, warn_count, pretty_reason
        )

        lines = [
            f"⚠️ Warned {member.mention}.",
            f"**Reason:** {pretty_reason}",
            f"**Total warnings:** {warn_count}",
        ]

        # Show the next configured threshold so staff knows what's coming
        future = sorted(t for t in self.escalation if t > warn_count)
        if future:
            nxt  = future[0]
            rule = self.escalation[nxt]
            act  = rule["action"]
            dur  = rule.get("duration")
            nxt_str = f"mute ({human_duration(dur)})" if act == "mute" and dur else "ban"
            lines.append(f"**Next threshold:** {nxt} warnings → {nxt_str}")

        if escalation_msg:
            lines.append(f"\n{escalation_msg}")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="warnings", description="View all warnings for a member. Staff only.")
    @app_commands.describe(member="Member to look up")
    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        warns = await self._get_warnings(interaction.guild.id, member.id)

        if not warns:
            return await interaction.followup.send(
                f"{member.mention} has no warnings.", ephemeral=True
            )

        emb = discord.Embed(
            title=f"⚠️  Warnings — {member.display_name}",
            colour=discord.Colour(INFO_COLOR),
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_thumbnail(url=member.display_avatar.url)
        emb.add_field(name="Total", value=str(len(warns)), inline=True)
        emb.add_field(name="User",  value=member.mention,  inline=True)
        emb.add_field(name="ID",    value=str(member.id),  inline=True)

        # Cap display at 10 most recent
        display = warns[-10:]
        for i, w in enumerate(display, start=len(warns) - len(display) + 1):
            try:
                ts     = datetime.fromisoformat(w["timestamp"].replace("Z", "+00:00"))
                ts_str = f"<t:{int(ts.timestamp())}:R>"
            except Exception:
                ts_str = "Unknown"

            mod_name = w.get("moderator_name", "Unknown")
            emb.add_field(
                name  = f"Warning #{i}",
                value = f"**Reason:** {w['reason']}\n**By:** {mod_name} • {ts_str}",
                inline= False,
            )

        footer = (
            f"Showing most recent 10 of {len(warns)} warnings"
            if len(warns) > 10
            else f"{len(warns)} warning(s) total"
        )
        emb.set_footer(text=footer)

        await interaction.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(name="clearwarns", description="Clear all warnings for a member. Staff only.")
    @app_commands.describe(member="Member to clear warnings for")
    async def clearwarns(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        removed = await self._clear_warnings(interaction.guild.id, member.id)

        if removed == 0:
            return await interaction.followup.send(
                f"{member.mention} has no warnings to clear.", ephemeral=True
            )

        await self._send_case_log(
            action    = "clearwarns",
            color     = CLEAR_COLOR,
            moderator = interaction.user,
            offender  = member,
            reason    = f"Cleared {removed} warning(s)",
            extra     = {"Warnings Removed": str(removed)},
        )

        await interaction.followup.send(
            f"✅ Cleared **{removed}** warning(s) from {member.mention}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WarnCog(bot))
