from __future__ import annotations

"""
cogs/staff_activity.py
──────────────────────
Passively tracks staff activity across the server and surfaces it via
/staffactivity. No commands for staff to game — it watches events silently.

What gets tracked:
  - Ticket claims         (TicketActionsView fires cog event)
  - Ticket closes         (same)
  - Messages in staff-monitored channels (configurable)
  - Slash command usage   (on_interaction listener)
  - Warns issued          (on_warn_issued cog event, fired from WarnCog)
  - Mutes/kicks/bans      (on_interaction, filtered by command name)

All counts live in /data/staff_activity.json and reset on a configurable
schedule (daily/weekly/never) set via STAFF_ACTIVITY_RESET env var.

──────────────────────────────────────────────────────────────────────────────
CONFIGURATION
──────────────────────────────────────────────────────────────────────────────

In your .env:

  # Comma-separated channel IDs that count as "support activity"
  # Messages posted in these channels increment the staff member's count.
  # Typically: your ticket category channels, support chat, staff chat.
  STAFF_ACTIVITY_CHANNELS=123456789,987654321

  # How often to auto-reset counts. Options: daily, weekly, never
  # "never" means counts accumulate until a manual /staffactivity reset
  STAFF_ACTIVITY_RESET=weekly

  # Day of week for weekly reset (0=Monday … 6=Sunday). Default: 0 (Monday)
  STAFF_ACTIVITY_RESET_DAY=0

Commands:
  /staffactivity report          — ranked leaderboard of staff activity
  /staffactivity user @member    — detailed breakdown for one staff member
  /staffactivity reset           — wipe all counts (owner only)
"""

import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed
from mangomods_bot.utils.log import log_action


# ── Config helpers ────────────────────────────────────────────────────────────

def _activity_channels() -> set[int]:
    raw = os.getenv("STAFF_ACTIVITY_CHANNELS", "")
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                out.add(int(part))
            except Exception:
                pass
    return out


def _reset_mode() -> str:
    return os.getenv("STAFF_ACTIVITY_RESET", "weekly").strip().lower()


def _reset_day() -> int:
    try:
        return max(0, min(6, int(os.getenv("STAFF_ACTIVITY_RESET_DAY", "0"))))
    except Exception:
        return 0


# ── Action keys — what we track ───────────────────────────────────────────────

# Each key maps to a human-readable label shown in /staffactivity report
ACTION_LABELS: dict[str, str] = {
    "ticket_claim":    "Tickets Claimed",
    "ticket_close":    "Tickets Closed",
    "message":         "Support Messages",
    "command":         "Commands Used",
    "warn":            "Warns Issued",
    "mute":            "Mutes Issued",
    "kick":            "Kicks Issued",
    "ban":             "Bans Issued",
    "ticket_note":     "Ticket Notes Added",
}

# Commands that count as moderation actions (mapped to action key)
MOD_COMMANDS: dict[str, str] = {
    "warn":     "warn",
    "mute":     "mute",
    "timeout":  "mute",
    "kick":     "kick",
    "softban":  "kick",
    "ban":      "ban",
}


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────

class StaffActivity(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot              = bot
        self.store            = JSONStore("/data/staff_activity.json", {
            "counts":       {},   # { staff_id: { action_key: int } }
            "last_reset":   None, # ISO timestamp of last reset
            "period_start": None, # ISO timestamp of current period start
        })
        self._lock            = asyncio.Lock()
        self._activity_chs    = _activity_channels()
        self._reset_mode      = _reset_mode()
        self._reset_day       = _reset_day()

    async def cog_load(self) -> None:
        # Initialise period_start if missing
        data = await self.store.read()
        if not data.get("period_start"):
            data["period_start"] = datetime.now(timezone.utc).isoformat()
            await self.store.write(data)

        if self._reset_mode in {"daily", "weekly"}:
            self.auto_reset.start()

    async def cog_unload(self) -> None:
        if self.auto_reset.is_running():
            self.auto_reset.cancel()

    # ── Staff check ───────────────────────────────────────────────────────────

    def _is_staff(self, member: discord.Member) -> bool:
        return any(
            r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id}
            for r in member.roles
        )

    def _is_owner(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.owner_role_id for r in member.roles)

    # ── Core increment ────────────────────────────────────────────────────────

    async def _increment(self, staff_id: int, action: str, amount: int = 1) -> None:
        async with self._lock:
            data = await self.store.read()
            key  = str(staff_id)
            data.setdefault("counts", {}).setdefault(key, {})
            data["counts"][key][action] = data["counts"][key].get(action, 0) + amount
            await self.store.write(data)

    # ── Auto-reset task ───────────────────────────────────────────────────────

    @tasks.loop(hours=1)
    async def auto_reset(self) -> None:
        now  = datetime.now(timezone.utc)
        data = await self.store.read()

        period_start_str = data.get("period_start")
        if not period_start_str:
            data["period_start"] = now.isoformat()
            await self.store.write(data)
            return

        try:
            period_start = datetime.fromisoformat(period_start_str)
        except Exception:
            data["period_start"] = now.isoformat()
            await self.store.write(data)
            return

        should_reset = False

        if self._reset_mode == "daily":
            # Reset once per day — when we cross midnight UTC
            if now.date() > period_start.date():
                should_reset = True

        elif self._reset_mode == "weekly":
            # Reset on the configured day of week, once per week
            days_since = (now - period_start).days
            if days_since >= 7 and now.weekday() == self._reset_day:
                should_reset = True

        if should_reset:
            await self._do_reset(actor="auto")

    @auto_reset.before_loop
    async def before_auto_reset(self) -> None:
        await self.bot.wait_until_ready()

    async def _do_reset(self, actor: str = "unknown") -> None:
        async with self._lock:
            data = await self.store.read()
            data["counts"]       = {}
            data["last_reset"]   = datetime.now(timezone.utc).isoformat()
            data["period_start"] = datetime.now(timezone.utc).isoformat()
            await self.store.write(data)

        await log_action(
            self.bot,
            "Staff Activity Reset",
            f"Counts reset by **{actor}**.",
        )

    # ── Listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Count messages posted by staff in monitored support channels."""
        if message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return
        if not self._is_staff(message.author):
            return
        if message.channel.id not in self._activity_chs:
            return

        await self._increment(message.author.id, "message")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """
        Count slash command usage by staff.
        Also catches specific mod commands for their own action keys.
        """
        if interaction.type != discord.InteractionType.application_command:
            return
        if not isinstance(interaction.user, discord.Member):
            return
        if not self._is_staff(interaction.user):
            return

        # General command count
        await self._increment(interaction.user.id, "command")

        # Specific mod commands
        cmd_name = (interaction.data or {}).get("name", "")
        if cmd_name in MOD_COMMANDS:
            await self._increment(interaction.user.id, MOD_COMMANDS[cmd_name])

    # ── Public methods called by other cogs ───────────────────────────────────
    # These let tickets.py and warnings.py fire events into this cog
    # without a hard import dependency.

    async def record_ticket_claim(self, staff_id: int) -> None:
        await self._increment(staff_id, "ticket_claim")

    async def record_ticket_close(self, staff_id: int) -> None:
        await self._increment(staff_id, "ticket_close")

    async def record_ticket_note(self, staff_id: int) -> None:
        await self._increment(staff_id, "ticket_note")

    # ──────────────────────────────────────────────────────────────────────────
    # Commands
    # ──────────────────────────────────────────────────────────────────────────

    group = app_commands.Group(
        name="staffactivity",
        description="Staff activity tracking.",
    )

    @group.command(name="report", description="Ranked staff activity report. Staff only.")
    async def report(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        data   = await self.store.read()
        counts = data.get("counts", {})

        if not counts:
            return await interaction.followup.send(
                "No activity data yet — counts populate as staff use commands and post in support channels.",
                ephemeral=True,
            )

        # Build total score per staff member (simple sum of all actions)
        scores: list[tuple[int, dict[str, int]]] = []
        for uid_str, actions in counts.items():
            total = sum(actions.values())
            if total > 0:
                scores.append((int(uid_str), actions))

        scores.sort(key=lambda x: sum(x[1].values()), reverse=True)

        period_start_str = data.get("period_start")
        period_str = ""
        if period_start_str:
            try:
                ps = datetime.fromisoformat(period_start_str)
                period_str = f"Since <t:{int(ps.timestamp())}:D>"
            except Exception:
                pass

        reset_note = ""
        if self._reset_mode != "never":
            reset_note = f" | Resets: **{self._reset_mode}**"

        emb = mango_embed(
            self.bot,
            title  = "📊  Staff Activity Report",
            color  = "info",
            footer = "Staff Activity",
        )
        emb.description = f"{period_str}{reset_note}" if (period_str or reset_note) else None

        medals = ["🥇", "🥈", "🥉"]

        for rank, (uid, actions) in enumerate(scores[:15]):
            prefix = medals[rank] if rank < 3 else f"**#{rank+1}**"
            total  = sum(actions.values())

            # Top 3 action types for this staff member
            top_actions = sorted(actions.items(), key=lambda kv: kv[1], reverse=True)[:3]
            action_str  = " | ".join(
                f"{ACTION_LABELS.get(k, k)}: **{v}**" for k, v in top_actions
            )

            emb.add_field(
                name  = f"{prefix}  <@{uid}>  (Total: {total})",
                value = action_str or "*No recorded actions*",
                inline= False,
            )

        if len(scores) > 15:
            emb.set_footer(text=f"MangoMods  •  Showing top 15 of {len(scores)} staff members")

        await interaction.followup.send(embed=emb, ephemeral=True)

    @group.command(name="user", description="Detailed activity breakdown for a staff member.")
    @app_commands.describe(member="Staff member to look up")
    async def user_report(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        data    = await self.store.read()
        actions = data.get("counts", {}).get(str(member.id), {})
        total   = sum(actions.values())

        emb = mango_embed(
            self.bot,
            title  = f"📋  Activity — {member.display_name}",
            color  = "info",
            footer = "Staff Activity",
        )
        emb.set_thumbnail(url=member.display_avatar.url)
        emb.add_field(name="Member",        value=member.mention, inline=True)
        emb.add_field(name="Total Actions", value=str(total),     inline=True)
        emb.add_field(name="\u200b",        value="\u200b",       inline=True)

        if not actions:
            emb.description = "No activity recorded for this period."
        else:
            for action_key, label in ACTION_LABELS.items():
                val = actions.get(action_key, 0)
                if val > 0:
                    emb.add_field(name=label, value=str(val), inline=True)

        period_start_str = data.get("period_start")
        if period_start_str:
            try:
                ps = datetime.fromisoformat(period_start_str)
                emb.add_field(
                    name  = "Period Start",
                    value = f"<t:{int(ps.timestamp())}:D>",
                    inline= False,
                )
            except Exception:
                pass

        await interaction.followup.send(embed=emb, ephemeral=True)

    @group.command(name="reset", description="Reset all staff activity counts. Owner only.")
    async def reset(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not self._is_owner(interaction.user):
            return await interaction.response.send_message("Owner only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        await self._do_reset(actor=str(interaction.user))

        await interaction.followup.send(
            "✅ All staff activity counts reset.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StaffActivity(bot))
