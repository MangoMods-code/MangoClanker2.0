from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

import discord
from discord import app_commands
from discord.ext import commands, tasks

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.log import log_action

# Accepts: 10m, 2h, 7d, 3w, 2mo, 1y
_DURATION_RE = re.compile(r"^\s*(\d+)\s*(s|m|h|d|w|mo|y)\s*$", re.IGNORECASE)

MAX_DAYS = 366
MAX_DURATION = timedelta(days=MAX_DAYS)


def parse_duration(text: str) -> Optional[timedelta]:
    m = _DURATION_RE.match(text or "")
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    if n <= 0:
        return None

    if unit == "s":
        td = timedelta(seconds=n)
    elif unit == "m":
        td = timedelta(minutes=n)
    elif unit == "h":
        td = timedelta(hours=n)
    elif unit == "d":
        td = timedelta(days=n)
    elif unit == "w":
        td = timedelta(weeks=n)
    elif unit == "mo":
        td = timedelta(days=30 * n)
    elif unit == "y":
        td = timedelta(days=365 * n)
    else:
        return None

    return td


def ts(dt: datetime) -> str:
    # Discord timestamp
    return f"<t:{int(dt.timestamp())}:R>"


class TempRole(commands.GroupCog, name="temprole"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store = JSONStore("/data/temproles.json", {"assignments": []})
        self.sweeper.start()

    def cog_unload(self) -> None:
        self.sweeper.cancel()

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.staff_role_id for r in member.roles)

    async def _ephemeral(self, interaction: discord.Interaction, content: str) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True)
        else:
            await interaction.response.send_message(content, ephemeral=True)

    async def _add_assignment(self, guild_id: int, user_id: int, role_id: int, expires_at: str) -> None:
        data = await self.store.read()
        data.setdefault("assignments", [])

        # Replace existing assignment for same guild/user/role
        data["assignments"] = [
            a for a in data["assignments"]
            if not (int(a.get("guild_id", 0)) == guild_id and int(a.get("user_id", 0)) == user_id and int(a.get("role_id", 0)) == role_id)
        ]
        data["assignments"].append({
            "guild_id": guild_id,
            "user_id": user_id,
            "role_id": role_id,
            "expires_at": expires_at,
        })
        await self.store.write(data)

    async def _remove_assignment(self, guild_id: int, user_id: int, role_id: int) -> None:
        data = await self.store.read()
        data.setdefault("assignments", [])
        data["assignments"] = [
            a for a in data["assignments"]
            if not (int(a.get("guild_id", 0)) == guild_id and int(a.get("user_id", 0)) == user_id and int(a.get("role_id", 0)) == role_id)
        ]
        await self.store.write(data)

    async def _get_assignments_for_member(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        data = await self.store.read()
        out = []
        for a in data.get("assignments", []):
            if int(a.get("guild_id", 0)) == guild_id and int(a.get("user_id", 0)) == user_id:
                out.append(a)
        return out

    # -------------------
    # Commands
    # -------------------
    @app_commands.command(name="add", description="Give a role temporarily (up to 366 days). Staff only.")
    @app_commands.describe(member="Member to give role to", role="Role to assign", duration="e.g. 10m, 2h, 7d, 3w, 2mo, 1y", reason="Optional reason")
    async def add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role, duration: str, reason: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        td = parse_duration(duration)
        if not td:
            return await self._ephemeral(interaction, "Invalid duration. Examples: `10m`, `2h`, `7d`, `3w`, `2mo`, `1y`.")
        if td > MAX_DURATION:
            return await self._ephemeral(interaction, f"Max duration is **{MAX_DAYS} days**.")

        # hierarchy check
        me = interaction.guild.me
        if me and role >= me.top_role:
            return await self._ephemeral(interaction, "I can't assign that role (role hierarchy).")

        try:
            await member.add_roles(role, reason=reason or f"TempRole added by {interaction.user} ({interaction.user.id})")
        except discord.Forbidden:
            return await self._ephemeral(interaction, "I don't have permission to add that role.")
        except Exception:
            return await self._ephemeral(interaction, "Failed to assign role (unexpected error).")

        expires = datetime.now(timezone.utc) + td
        await self._add_assignment(interaction.guild.id, member.id, role.id, expires.isoformat())

        await log_action(
            self.bot,
            "Temp Role Added",
            f"Staff: {interaction.user.mention}\nMember: {member.mention}\nRole: {role.mention}\nExpires: {ts(expires)}\nReason: {reason or 'No reason provided.'}"
        )

        await interaction.followup.send(
            f"✅ Gave {role.mention} to {member.mention} until {ts(expires)}.",
            ephemeral=True
        )

    @app_commands.command(name="remove", description="Remove a temp role early. Staff only.")
    @app_commands.describe(member="Member", role="Role", reason="Optional reason")
    async def remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role, reason: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await member.remove_roles(role, reason=reason or f"TempRole removed by {interaction.user} ({interaction.user.id})")
        except Exception:
            # still remove the assignment even if role isn't present
            pass

        await self._remove_assignment(interaction.guild.id, member.id, role.id)

        await log_action(
            self.bot,
            "Temp Role Removed",
            f"Staff: {interaction.user.mention}\nMember: {member.mention}\nRole: {role.mention}\nReason: {reason or 'No reason provided.'}"
        )

        await interaction.followup.send(f"✅ Removed {role.mention} from {member.mention}.", ephemeral=True)

    @app_commands.command(name="list", description="List active temp roles for a member. Staff only.")
    @app_commands.describe(member="Member")
    async def list(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        assigns = await self._get_assignments_for_member(interaction.guild.id, member.id)
        if not assigns:
            return await interaction.followup.send("No active temp roles for that member.", ephemeral=True)

        lines = []
        for a in assigns:
            rid = int(a.get("role_id", 0))
            role = interaction.guild.get_role(rid)
            try:
                exp = datetime.fromisoformat(str(a.get("expires_at")).replace("Z", "+00:00"))
            except Exception:
                continue
            lines.append(f"- {role.mention if role else f'`{rid}`'} expires {ts(exp)}")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # -------------------
    # Sweeper
    # -------------------
    @tasks.loop(seconds=60)
    async def sweeper(self):
        data = await self.store.read()
        assigns: List[Dict[str, Any]] = data.get("assignments", [])
        if not assigns:
            return

        now = datetime.now(timezone.utc)
        remaining: List[Dict[str, Any]] = []

        for a in assigns:
            try:
                gid = int(a["guild_id"])
                uid = int(a["user_id"])
                rid = int(a["role_id"])
                exp = datetime.fromisoformat(str(a["expires_at"]).replace("Z", "+00:00"))
            except Exception:
                continue

            if exp > now:
                remaining.append(a)
                continue

            guild = self.bot.get_guild(gid)
            if not guild:
                continue

            role = guild.get_role(rid)
            if not role:
                # role deleted; drop assignment
                continue

            try:
                member = guild.get_member(uid) or await guild.fetch_member(uid)
                await member.remove_roles(role, reason="TempRole expired")
            except Exception:
                # if we failed to remove (permissions/outage), keep it to retry next loop
                remaining.append(a)

        if remaining != assigns:
            await self.store.write({"assignments": remaining})

    @sweeper.before_loop
    async def before_sweeper(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TempRole(bot))