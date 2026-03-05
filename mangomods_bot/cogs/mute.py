from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

import discord
from discord import app_commands
from discord.ext import commands, tasks

from mangomods_bot.storage import JSONStore

_DURATION_RE = re.compile(r"^\s*(\d+)\s*(s|m|h|d|w|mo|y)\s*$", re.IGNORECASE)
MAX_TIMEOUT = timedelta(days=28)  # Discord hard limit

CASE_COLORS = {
    "mute": 0xF9A826,      # mango gold
    "timeout": 0x5865F2,   # blurple
    "ban": 0xED4245,       # red
    "unmute": 0x57F287,    # green
}


def parse_duration(text: str) -> Optional[timedelta]:
    """
    Accepts: 10m, 2h, 7d, 3w, 2mo, 1y
    Notes:
      - mo = 30 days
      - y  = 365 days
    """
    m = _DURATION_RE.match(text or "")
    if not m:
        return None

    n = int(m.group(1))
    unit = m.group(2).lower()
    if n <= 0:
        return None

    if unit == "s":
        return timedelta(seconds=n)
    if unit == "m":
        return timedelta(minutes=n)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    if unit == "w":
        return timedelta(weeks=n)
    if unit == "mo":
        return timedelta(days=30 * n)
    if unit == "y":
        return timedelta(days=365 * n)

    return None


def human_duration(td: timedelta) -> str:
    seconds = int(td.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


class MuteCog(commands.Cog):
    """
    /mute     -> staff-only native timeout (<= 28 days; errors if bigger)
    /timeout  -> owner-only: <=28d native timeout, >28d muted-role fallback
    /unmute   -> staff-only: remove native timeout and/or muted role
    /ban      -> owner-only ban
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.long_store = JSONStore("/data/long_mutes.json", {"mutes": []})
        self.case_store = JSONStore("/data/mod_cases.json", {"next_case": 1})
        self.long_mute_watcher.start()

    def cog_unload(self) -> None:
        self.long_mute_watcher.cancel()

    # -----------------------------
    # Permissions / helpers
    # -----------------------------
    async def _is_staff(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.staff_role_id for r in member.roles)

    async def _is_owner_role(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.owner_role_id for r in member.roles)

    def _muted_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        rid = getattr(self.bot.config, "muted_role_id", None)
        if not rid:
            return None
        return guild.get_role(rid)

    async def _safe_defer(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass

    async def _ephemeral(self, interaction: discord.Interaction, content: str) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(content, ephemeral=True)
            except Exception:
                pass

    def _hierarchy_blocked(self, guild: discord.Guild, target: discord.Member) -> bool:
        me = guild.me
        if not me:
            return False
        return target.top_role >= me.top_role

    # -----------------------------
    # Carl-like case logging
    # -----------------------------
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
        moderator: discord.Member,
        offender: discord.Member | discord.User,
        reason: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        case_no = await self._next_case()
        color = CASE_COLORS.get(action, 0x2B2D31)

        emb = discord.Embed(
            title=f"{action} | case {case_no}",
            colour=discord.Colour(color),
            timestamp=datetime.now(timezone.utc),
        )
        emb.add_field(name="Offender", value=f"{offender.mention} ({offender})", inline=False)
        emb.add_field(name="Reason", value=reason if reason.strip() else "No reason given.", inline=False)
        emb.add_field(name="Responsible moderator", value=f"{moderator.mention} ({moderator})", inline=False)
        emb.add_field(name="ID", value=str(offender.id), inline=False)

        if extra:
            for k, v in extra.items():
                emb.add_field(name=k, value=v, inline=False)

        emb.set_footer(text=f"Today • case {case_no}")

        ch = self.bot.get_channel(self.bot.config.log_channel_id)
        if ch is None:
            ch = await self.bot.fetch_channel(self.bot.config.log_channel_id)
        if isinstance(ch, discord.TextChannel):
            await ch.send(embed=emb)

    # -----------------------------
    # Long mute persistence helpers
    # -----------------------------
    async def _add_long_mute(self, guild_id: int, user_id: int, until_iso: str) -> None:
        data = await self.long_store.read()
        data.setdefault("mutes", [])
        data["mutes"] = [
            m for m in data["mutes"]
            if not (m.get("guild_id") == guild_id and m.get("user_id") == user_id)
        ]
        data["mutes"].append({"guild_id": guild_id, "user_id": user_id, "until": until_iso})
        await self.long_store.write(data)

    async def _remove_long_mute(self, guild_id: int, user_id: int) -> None:
        data = await self.long_store.read()
        data.setdefault("mutes", [])
        data["mutes"] = [
            m for m in data["mutes"]
            if not (m.get("guild_id") == guild_id and m.get("user_id") == user_id)
        ]
        await self.long_store.write(data)

    @tasks.loop(seconds=60)
    async def long_mute_watcher(self):
        data = await self.long_store.read()
        mutes: List[Dict[str, Any]] = data.get("mutes", [])
        if not mutes:
            return

        now = datetime.now(timezone.utc)
        remaining: List[Dict[str, Any]] = []

        for entry in mutes:
            try:
                gid = int(entry["guild_id"])
                uid = int(entry["user_id"])
                until = datetime.fromisoformat(str(entry["until"]).replace("Z", "+00:00"))
            except Exception:
                continue

            if until > now:
                remaining.append(entry)
                continue

            guild = self.bot.get_guild(gid)
            if not guild:
                continue

            role = self._muted_role(guild)
            if not role:
                continue

            try:
                member = guild.get_member(uid) or await guild.fetch_member(uid)
                await member.remove_roles(role, reason="Long timeout expired")
            except Exception:
                remaining.append(entry)

        if remaining != mutes:
            await self.long_store.write({"mutes": remaining})

    @long_mute_watcher.before_loop
    async def before_long_mute_watcher(self):
        await self.bot.wait_until_ready()

    # -----------------------------
    # Commands
    # -----------------------------
    @app_commands.command(name="mute", description="Mute (timeout) a member for up to 28 days. Staff only.")
    @app_commands.describe(member="Member to mute", duration="e.g. 10m, 2h, 7d, 4w", reason="Optional reason")
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await self._safe_defer(interaction)

        td = parse_duration(duration)
        if not td:
            return await self._ephemeral(interaction, "Invalid duration. Examples: `10m`, `2h`, `7d`, `4w`.")
        if td > MAX_TIMEOUT:
            return await self._ephemeral(interaction, "Discord timeouts can’t exceed **28 days**. Use a shorter duration.")

        if member.id == interaction.user.id:
            return await self._ephemeral(interaction, "You can’t mute yourself.")
        if self._hierarchy_blocked(interaction.guild, member):
            return await self._ephemeral(interaction, "I can’t mute that member (role hierarchy).")

        pretty_reason = reason.strip() if reason and reason.strip() else "No reason given."

        try:
            await member.timeout(td, reason=pretty_reason)
        except discord.Forbidden:
            return await self._ephemeral(interaction, "I don’t have permission to timeout that member.")
        except Exception:
            return await self._ephemeral(interaction, "Failed to mute member (unexpected error).")

        await self._send_case_log(
            action="mute",
            moderator=interaction.user,
            offender=member,
            reason=pretty_reason,
            extra={"Duration": human_duration(td)},
        )

        await self._ephemeral(interaction, f"✅ Muted {member.mention} for **{human_duration(td)}**.\nReason: {pretty_reason}")

    @app_commands.command(name="timeout", description="Timeout-like action with longer durations (owner only).")
    @app_commands.describe(member="Member to timeout", duration="e.g. 10m, 2h, 7d, 2mo, 1y", reason="Optional reason")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_owner_role(interaction.user):
            return await self._ephemeral(interaction, "Owner role only.")

        await self._safe_defer(interaction)

        td = parse_duration(duration)
        if not td:
            return await self._ephemeral(interaction, "Invalid duration. Examples: `10m`, `2h`, `7d`, `4w`, `2mo`, `1y`.")

        if member.id == interaction.user.id:
            return await self._ephemeral(interaction, "You can’t timeout yourself.")
        if self._hierarchy_blocked(interaction.guild, member):
            return await self._ephemeral(interaction, "I can’t timeout that member (role hierarchy).")

        pretty_reason = reason.strip() if reason and reason.strip() else "No reason given."

        # Native timeout (<=28d)
        if td <= MAX_TIMEOUT:
            try:
                await member.timeout(td, reason=pretty_reason)
            except discord.Forbidden:
                return await self._ephemeral(interaction, "I don’t have permission to timeout that member.")
            except Exception:
                return await self._ephemeral(interaction, "Failed to timeout member (unexpected error).")

            await self._send_case_log(
                action="timeout",
                moderator=interaction.user,
                offender=member,
                reason=pretty_reason,
                extra={"Duration": human_duration(td), "Mode": "native"},
            )
            return await self._ephemeral(interaction, f"✅ Timed out {member.mention} for **{human_duration(td)}**.\nReason: {pretty_reason}")

        # Long duration (>28d): muted role fallback
        role = self._muted_role(interaction.guild)
        if not role:
            return await self._ephemeral(interaction, "Set `MUTED_ROLE_ID` in `.env` to use long timeouts (>28d).")

        try:
            await member.add_roles(role, reason=pretty_reason)
        except discord.Forbidden:
            return await self._ephemeral(interaction, "I don’t have permission to assign the muted role.")
        except Exception:
            return await self._ephemeral(interaction, "Failed to apply long timeout (unexpected error).")

        until = datetime.now(timezone.utc) + td
        await self._add_long_mute(interaction.guild.id, member.id, until.isoformat())

        await self._send_case_log(
            action="timeout",
            moderator=interaction.user,
            offender=member,
            reason=pretty_reason,
            extra={"Duration": human_duration(td), "Mode": "role-based"},
        )

        await self._ephemeral(interaction, f"✅ Long-timeout applied to {member.mention} for **{human_duration(td)}** (role-based).\nReason: {pretty_reason}")

    @app_commands.command(name="unmute", description="Remove timeout and/or long-timeout role. Staff only.")
    @app_commands.describe(member="Member to unmute", reason="Optional reason")
    async def unmute(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await self._safe_defer(interaction)

        pretty_reason = reason.strip() if reason and reason.strip() else "No reason given."

        # Remove native timeout
        try:
            await member.timeout(None, reason=pretty_reason)
        except Exception:
            pass

        # Remove muted role if present
        role = self._muted_role(interaction.guild)
        if role:
            try:
                await member.remove_roles(role, reason=pretty_reason)
            except Exception:
                pass

        await self._remove_long_mute(interaction.guild.id, member.id)

        await self._send_case_log(
            action="unmute",
            moderator=interaction.user,
            offender=member,
            reason=pretty_reason,
        )

        await self._ephemeral(interaction, f"✅ Unmuted {member.mention}.\nReason: {pretty_reason}")

    @app_commands.command(name="ban", description="Ban a member. Owner role only.")
    @app_commands.describe(member="Member to ban", delete_message_days="Delete messages from last N days (0-7)", reason="Optional reason")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, delete_message_days: Optional[int] = 0, reason: Optional[str] = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_owner_role(interaction.user):
            return await self._ephemeral(interaction, "Owner role only.")

        await self._safe_defer(interaction)

        dmd = int(delete_message_days or 0)
        if dmd < 0 or dmd > 7:
            return await self._ephemeral(interaction, "delete_message_days must be between 0 and 7.")

        if member.id == interaction.user.id:
            return await self._ephemeral(interaction, "You can’t ban yourself.")
        if self._hierarchy_blocked(interaction.guild, member):
            return await self._ephemeral(interaction, "I can’t ban that member (role hierarchy).")

        pretty_reason = reason.strip() if reason and reason.strip() else "No reason given."

        try:
            await interaction.guild.ban(
                member,
                reason=pretty_reason,
                delete_message_days=dmd,
            )
        except discord.Forbidden:
            return await self._ephemeral(interaction, "I don’t have permission to ban that member.")
        except Exception:
            return await self._ephemeral(interaction, "Failed to ban member (unexpected error).")

        await self._send_case_log(
            action="ban",
            moderator=interaction.user,
            offender=member,
            reason=pretty_reason,
            extra={"Delete Msg Days": str(dmd)},
        )

        await self._ephemeral(interaction, f"✅ Banned {member.mention}.\nReason: {pretty_reason}")


async def setup(bot: commands.Bot):
    await bot.add_cog(MuteCog(bot))