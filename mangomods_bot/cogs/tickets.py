from __future__ import annotations

import asyncio
import io
import html
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed, brand_color
from mangomods_bot.utils.log import log_action
from mangomods_bot.utils.misc import iso_now, pretty_dt, sanitize_channel_name, extract_user_id
from mangomods_bot.views.ticket_panel import TicketPanelView
from mangomods_bot.views.ticket_actions import TicketActionsView
from mangomods_bot.views.ticket_rating import TicketRatingView


# ── Priority configuration ───────────────────────────────────────────────────

PRIORITY_COLORS: dict[str, discord.Colour] = {
    "low":    discord.Colour(0x57F287),  # green
    "medium": discord.Colour(0xF9A826),  # mango gold
    "high":   discord.Colour(0xFF7043),  # deep orange
    "urgent": discord.Colour(0xED4245),  # red
}

PRIORITY_LABELS: dict[str, str] = {
    "low":    "🟢  Low",
    "medium": "🟡  Medium",
    "high":   "🔴  High",
    "urgent": "🚨  Urgent",
}

PRIORITY_HTML_COLORS: dict[str, str] = {
    "low":    "#57F287",
    "medium": "#F9A826",
    "high":   "#FF7043",
    "urgent": "#ED4245",
}

TYPE_EMOJIS: dict[str, str] = {
    "purchase": "🛒",
    "support":  "🔧",
    "general":  "💬",
}


# ── Utility functions ────────────────────────────────────────────────────────

def _fmt_duration(seconds: float) -> str:
    """Convert a float number of seconds into a human-readable duration string."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m = s // 60
    if m < 60:
        return f"{m}m"
    h = m // 60
    rem_m = m % 60
    if h < 24:
        return f"{h}h {rem_m}m" if rem_m else f"{h}h"
    d = h // 24
    rem_h = h % 24
    return f"{d}d {rem_h}h" if rem_h else f"{d}d"


def _fmt_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── HTML transcript builder ──────────────────────────────────────────────────

def _build_transcript_html(
    *,
    guild: discord.Guild,
    channel: discord.TextChannel,
    messages: list[discord.Message],
    website_url: str,
    summary: dict[str, str],
    notes: list[dict[str, Any]],
    priority: str,
    rating: Optional[int],
) -> str:
    priority_color = PRIORITY_HTML_COLORS.get(priority, "#F9A826")
    priority_label = PRIORITY_LABELS.get(priority, priority.title()).replace("  ", " ")

    css = """
    :root{
      --bg:#0b0f14; --panel:#0f1623; --panel2:#101a2a; --border:#263043;
      --text:#e6edf3; --muted:rgba(230,237,243,.72); --accent:#f9a826;
      --note:#9B59B6; --note-bg:rgba(155,89,182,.08);
    }
    *{box-sizing:border-box;}
    body{margin:0;background:var(--bg);color:var(--text);
         font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;}
    a{color:#7cc4ff;text-decoration:none;}
    .wrap{max-width:1020px;margin:0 auto;padding:24px 14px 48px;}

    /* Summary card */
    .card{border:1px solid var(--border);background:var(--panel);border-radius:14px;
          overflow:hidden;box-shadow:0 10px 40px rgba(0,0,0,.35);margin-bottom:20px;}
    .cardHead{padding:14px 18px;display:flex;justify-content:space-between;align-items:flex-start;
              background:rgba(255,255,255,.02);border-bottom:1px solid var(--border);}
    .cardHead h2{margin:0;font-size:15px;font-weight:800;}
    .cardHead .meta{color:var(--muted);font-size:12px;margin-top:4px;}
    .grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;padding:16px 18px;background:var(--panel2);}
    .kv{border:1px solid rgba(38,48,67,.9);background:rgba(0,0,0,.15);border-radius:10px;padding:10px 12px;}
    .k{font-size:11px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.04em;}
    .v{margin-top:5px;font-size:13px;font-weight:700;word-break:break-word;}
    .priority-badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;
                    font-weight:800;color:#0b0f14;}

    /* Notes section */
    .section{margin-bottom:18px;border:1px solid var(--border);border-radius:14px;overflow:hidden;}
    .sectionHead{padding:10px 16px;background:var(--note-bg);border-bottom:1px solid rgba(155,89,182,.25);
                 font-size:13px;font-weight:800;color:var(--note);}
    .noteItem{padding:12px 16px;border-bottom:1px solid var(--border);background:var(--note-bg);}
    .noteItem:last-child{border-bottom:none;}
    .noteAuthor{font-size:12px;font-weight:800;color:var(--note);}
    .noteWhen{font-size:11px;color:var(--muted);margin-left:8px;}
    .noteContent{margin-top:5px;font-size:13px;white-space:pre-wrap;line-height:1.4;}

    /* Message list */
    .msgList{border:1px solid var(--border);border-radius:14px;overflow:hidden;}
    .msgListHead{padding:10px 16px;background:rgba(255,255,255,.02);
                 border-bottom:1px solid var(--border);font-size:13px;font-weight:800;color:var(--muted);}
    .msg{display:flex;gap:12px;padding:12px 14px;border-bottom:1px solid #1c2533;
         background:rgba(255,255,255,.008);}
    .msg:last-child{border-bottom:none;}
    .av{width:38px;height:38px;border-radius:50%;flex:0 0 auto;object-fit:cover;}
    .who{font-weight:800;font-size:13px;}
    .when{margin-left:8px;font-size:11px;color:var(--muted);}
    .badge{display:inline-block;padding:1px 7px;border:1px solid var(--border);
           border-radius:999px;font-size:10px;color:var(--muted);margin-left:6px;}
    .content{margin-top:4px;white-space:pre-wrap;line-height:1.4;font-size:13px;
             color:rgba(230,237,243,.9);}
    .attachments{margin-top:6px;font-size:12px;color:var(--muted);}
    """

    def kv_box(k: str, v: str, color: str | None = None) -> str:
        v_html = (
            f'<span class="priority-badge" style="background:{color}">{html.escape(v)}</span>'
            if color else html.escape(v or "—")
        )
        return f'<div class="kv"><div class="k">{html.escape(k)}</div><div class="v">{v_html}</div></div>'

    summary_boxes = "".join([
        kv_box("Priority",            priority_label, priority_color),
        kv_box("Ticket Name",         summary.get("Ticket Name", "")),
        kv_box("Ticket Author",       summary.get("Ticket Author", "")),
        kv_box("Claimed By",          summary.get("Claimed By", "")),
        kv_box("Closed By",           summary.get("Closed By", "")),
        kv_box("Open Date",           summary.get("Open Date", "")),
        kv_box("Close Date",          summary.get("Close Date", "")),
        kv_box("Close Reason",        summary.get("Ticket Close Reason", "")),
        kv_box("Staff Message Count", summary.get("Staff Message Count", "")),
        kv_box("User Rating",         f"{'⭐' * rating} ({rating}/5)" if rating else "Not rated"),
        kv_box("Server",              guild.name),
    ])

    # Notes section HTML
    notes_html = ""
    if notes:
        note_items = ""
        for n in notes:
            ts_str = ""
            try:
                ts_dt = datetime.fromisoformat(n["timestamp"].replace("Z", "+00:00"))
                ts_str = _fmt_dt(ts_dt)
            except Exception:
                ts_str = n.get("timestamp", "")
            note_items += f"""
            <div class="noteItem">
              <div>
                <span class="noteAuthor">{html.escape(n.get('author_name','Staff'))}</span>
                <span class="noteWhen">{html.escape(ts_str)}</span>
              </div>
              <div class="noteContent">{html.escape(n.get('content',''))}</div>
            </div>
            """
        notes_html = f"""
        <div class="section">
          <div class="sectionHead">📝  Staff Notes ({len(notes)})</div>
          {note_items}
        </div>
        """

    # Message rows
    rows = []
    for m in messages:
        av = getattr(m.author.display_avatar, "url", "")
        name = getattr(m.author, "display_name", str(m.author))
        ts = _fmt_dt(m.created_at)
        content = m.content or ""

        if not content and m.embeds:
            parts = []
            for e in m.embeds:
                t = e.title or ""
                d = e.description or ""
                if t or d:
                    parts.append(f"[EMBED] {t}\n{d}".strip())
            content = "\n\n".join(parts)

        attach_lines = [
            f'📎 <a href="{html.escape(a.url)}">{html.escape(a.filename)}</a>'
            for a in m.attachments
        ]
        attach_html = f'<div class="attachments">{"<br/>".join(attach_lines)}</div>' if attach_lines else ""
        bot_badge = '<span class="badge">BOT</span>' if m.author.bot else ""

        rows.append(f"""
        <div class="msg">
          <img class="av" src="{html.escape(av)}" alt=""/>
          <div style="flex:1 1 auto;min-width:0;">
            <div><span class="who">{html.escape(name)}</span>{bot_badge}<span class="when">{html.escape(ts)}</span></div>
            <div class="content">{html.escape(content)}</div>
            {attach_html}
          </div>
        </div>
        """)

    exported = _fmt_dt(_now())
    ticket_name = html.escape(summary.get("Ticket Name", "MangoMods Transcript"))

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{ticket_name}</title>
  <style>{css}</style>
</head>
<body>
<div class="wrap">

  <div class="card">
    <div class="cardHead">
      <div>
        <h2>🎫  Ticket Closed — {ticket_name}</h2>
        <div class="meta">#{html.escape(channel.name)} &nbsp;•&nbsp; Exported: {html.escape(exported)} &nbsp;•&nbsp; <a href="{html.escape(website_url)}">{html.escape(website_url)}</a></div>
      </div>
    </div>
    <div class="grid">{summary_boxes}</div>
  </div>

  {notes_html}

  <div class="msgList">
    <div class="msgListHead">💬  Messages ({len(messages)})</div>
    {''.join(rows)}
  </div>

</div>
</body>
</html>"""


# ── Modals ───────────────────────────────────────────────────────────────────

class AddUserModal(discord.ui.Modal, title="Add User To Ticket"):
    user_input = discord.ui.TextInput(
        label="User ID or mention",
        placeholder="Paste a user ID or @mention",
        max_length=100,
    )

    def __init__(self, bot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        cog = self.bot.get_cog("ticket") or self.bot.get_cog("Tickets")
        if cog:
            await cog.add_user_to_ticket(interaction, str(self.user_input))


class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(
        label="Close reason (optional)",
        placeholder="Resolved / No answer / Duplicate / etc.",
        max_length=120,
        required=False,
    )

    def __init__(self, bot, channel_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        cog = self.bot.get_cog("ticket") or self.bot.get_cog("Tickets")
        if not cog:
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await cog.close_ticket(
            interaction,
            self.channel_id,
            str(self.reason).strip() or "No reason provided",
        )


class NoteModal(discord.ui.Modal, title="Add Staff Note"):
    note_text = discord.ui.TextInput(
        label="Note",
        placeholder="Internal staff note — visible in the ticket transcript",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )

    def __init__(self, bot, channel_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        cog = self.bot.get_cog("ticket") or self.bot.get_cog("Tickets")
        if cog:
            await cog._post_note(interaction, self.channel_id, str(self.note_text).strip())


# ── Cog ──────────────────────────────────────────────────────────────────────

class Tickets(commands.GroupCog, name="ticket", group_description="MangoMods ticket system — open, manage, and close support tickets."):
    """
    /ticket panel  — post the ticket panel (staff)
    /ticket note   — add a staff note to this ticket (staff)
    /ticket stats  — view ticket statistics (staff)
    Ticket opening is handled via the panel's Select → priority buttons → modals.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        self.ticket_store = JSONStore(
            "/data/tickets.json",
            {
                "open_tickets_by_user": {},
                "ticket_cooldowns": {},
                "tickets_completed": 0,
                "tickets_by_channel": {},
            },
        )
        self.panel_store = JSONStore(
            "/data/panels.json",
            {"ticket_panel": None, "status_panel": None},
        )
        self._panel_lock = asyncio.Lock()

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _ephemeral(self, interaction: discord.Interaction, content: str) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)
        except Exception:
            pass

    def _staff_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        return guild.get_role(self.bot.config.staff_role_id)

    async def _is_staff(self, member: discord.Member) -> bool:
        return any(r.id == self.bot.config.staff_role_id for r in member.roles)

    async def _is_owner_or_staff(self, interaction: discord.Interaction, owner_id: int) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.id == owner_id:
            return True
        return await self._is_staff(interaction.user)

    async def _get_open_ticket_channel(
        self, guild: discord.Guild, user_id: int
    ) -> Optional[discord.TextChannel]:
        data = await self.ticket_store.read()
        meta = data.get("open_tickets_by_user", {}).get(str(user_id))
        if not meta:
            return None
        ch = guild.get_channel(int(meta.get("channel_id", 0)))
        if isinstance(ch, discord.TextChannel):
            return ch
        # Stale entry — clean it up
        try:
            data["open_tickets_by_user"].pop(str(user_id), None)
            await self.ticket_store.write(data)
        except Exception:
            pass
        return None

    async def _cooldown_ok(self, user_id: int) -> tuple[bool, str]:
        secs = int(self.bot.config.ticket_cooldown_seconds or 0)
        if secs <= 0:
            return True, ""
        data = await self.ticket_store.read()
        last_iso = data.get("ticket_cooldowns", {}).get(str(user_id))
        if not last_iso:
            return True, ""
        try:
            last = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
            delta = (_now() - last).total_seconds()
            if delta < secs:
                remain = int(secs - delta)
                return False, f"Please wait **{remain}s** before opening another ticket."
        except Exception:
            pass
        return True, ""

    async def _get_or_create_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        if self.bot.config.tickets_category_id:
            cat = guild.get_channel(self.bot.config.tickets_category_id)
            if isinstance(cat, discord.CategoryChannel):
                return cat
        for c in guild.categories:
            if c.name.lower() == "tickets":
                return c
        return await guild.create_category("Tickets", reason="MangoMods ticket system")

    async def _unique_channel_name(self, guild: discord.Guild, base: str) -> str:
        existing = {c.name for c in guild.channels if isinstance(c, discord.TextChannel)}
        if base not in existing:
            return base
        i = 2
        while f"{base}-{i}" in existing:
            i += 1
        return f"{base}-{i}"

    async def _get_state(self, channel_id: int) -> Optional[dict[str, Any]]:
        data = await self.ticket_store.read()
        return data.get("tickets_by_channel", {}).get(str(channel_id))

    async def _set_state(self, channel_id: int, updates: dict[str, Any]) -> None:
        data = await self.ticket_store.read()
        data.setdefault("tickets_by_channel", {})
        cur = data["tickets_by_channel"].get(str(channel_id), {})
        cur.update(updates)
        data["tickets_by_channel"][str(channel_id)] = cur
        await self.ticket_store.write(data)

    async def _find_actions_message(
        self, channel: discord.TextChannel
    ) -> Optional[discord.Message]:
        """Find the most recent bot message in the channel that has our action buttons."""
        if not self.bot.user:
            return None
        async for m in channel.history(limit=30, oldest_first=False):
            if m.author.id != self.bot.user.id or not m.components:
                continue
            for row in m.components:
                for c in getattr(row, "children", []):
                    if getattr(c, "custom_id", "").startswith("mangomods:ticket:"):
                        return m
        return None

    async def _refresh_controls(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        locked: bool,
        closed: bool,
    ) -> None:
        """Update the control message so button states match the new ticket state."""
        new_view = TicketActionsView(self.bot, locked=locked, closed=closed)
        try:
            if interaction.message:
                await interaction.message.edit(view=new_view)
                return
        except Exception:
            pass
        try:
            msg = await self._find_actions_message(channel)
            if msg:
                await msg.edit(view=new_view)
        except Exception:
            pass

    # ── Panel embed builder ──────────────────────────────────────────────────

    def _build_panel_embed(self) -> discord.Embed:
        emb = discord.Embed(
            title="🥭  MangoMods — Support Tickets",
            description=(
                "Need help? We've got you covered. Select a ticket type from the menu below "
                "and a staff member will be with you as soon as possible.\n\n"
                f"🌐 **Website:** {self.bot.config.website_url}\n"
                "📋 **Please provide accurate info** so we can help you faster."
            ),
            colour=discord.Colour(0xF9A826),
            timestamp=_now(),
        )
        emb.add_field(
            name="📂  Ticket Types",
            value=(
                "🛒 **Purchase** — Buy a product or service\n"
                "🔧 **Support** — Get help with an existing product\n"
                "💬 **General** — Ask us anything else"
            ),
            inline=False,
        )
        emb.add_field(
            name="⚡  Priority Levels",
            value=(
                "🟢 Low · 🟡 Medium · 🔴 High · 🚨 Urgent\n"
                "*You'll choose a priority after selecting your ticket type.*"
            ),
            inline=False,
        )
        emb.set_footer(text="MangoMods  •  Ticket System")
        return emb

    # ── /ticket panel ────────────────────────────────────────────────────────

    @app_commands.command(name="panel", description="Post or update the MangoMods ticket panel (staff only).")
    @app_commands.describe(channel="Optional channel to post the panel in (defaults to current).")
    async def panel(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if self.bot.config.staff_role_id not in [r.id for r in interaction.user.roles]:
            return await self._ephemeral(interaction, "Staff only.")

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid channel.")

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        async with self._panel_lock:
            emb = self._build_panel_embed()
            view = TicketPanelView(self.bot)
            panels = await self.panel_store.read()
            existing = panels.get("ticket_panel")

            if existing:
                try:
                    old_ch = interaction.guild.get_channel(int(existing["channel_id"]))
                    if old_ch is None:
                        fetched = await self.bot.fetch_channel(int(existing["channel_id"]))
                        old_ch = fetched if isinstance(fetched, discord.TextChannel) else None

                    if isinstance(old_ch, discord.TextChannel):
                        old_msg = await old_ch.fetch_message(int(existing["message_id"]))
                        if old_ch.id != target.id:
                            try:
                                await old_msg.delete()
                            except Exception:
                                pass
                            new_msg = await target.send(embed=emb, view=view)
                            panels["ticket_panel"] = {"channel_id": target.id, "message_id": new_msg.id}
                            await self.panel_store.write(panels)
                            await log_action(self.bot, "Ticket Panel Moved", f"By {interaction.user.mention} to {target.mention}")
                            return await interaction.followup.send("✅ Ticket panel moved.", ephemeral=True)

                        await old_msg.edit(embed=emb, view=view)
                        await log_action(self.bot, "Ticket Panel Updated", f"By {interaction.user.mention}")
                        return await interaction.followup.send("✅ Ticket panel updated.", ephemeral=True)
                except Exception:
                    pass

            msg = await target.send(embed=emb, view=view)
            panels["ticket_panel"] = {"channel_id": target.id, "message_id": msg.id}
            await self.panel_store.write(panels)
            await log_action(self.bot, "Ticket Panel Posted", f"By {interaction.user.mention} in {target.mention}")
            await interaction.followup.send("✅ Ticket panel posted.", ephemeral=True)

    # ── Ticket creation ──────────────────────────────────────────────────────

    async def create_ticket(
        self,
        interaction: discord.Interaction,
        ticket_type: str,
        priority: str,
        fields: Dict[str, str],
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Tickets can only be opened in a server.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        user = interaction.user

        existing = await self._get_open_ticket_channel(guild, user.id)
        if existing:
            return await interaction.followup.send(
                f"You already have an open ticket: {existing.mention}", ephemeral=True
            )

        ok, msg = await self._cooldown_ok(user.id)
        if not ok:
            return await interaction.followup.send(msg, ephemeral=True)

        category = await self._get_or_create_category(guild)
        staff_role = self._staff_role(guild)
        if staff_role is None:
            return await interaction.followup.send("STAFF_ROLE_ID is invalid.", ephemeral=True)

        prefix = {"purchase": "purchase", "support": "support", "general": "general"}.get(
            ticket_type, "ticket"
        )
        base_name = f"{prefix}-{sanitize_channel_name(user.display_name)}"
        channel_name = await self._unique_channel_name(guild, base_name)

        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            staff_role: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
        }
        bot_member = guild.me or (guild.get_member(self.bot.user.id) if self.bot.user else None)
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"MangoMods ticket • type={ticket_type} • priority={priority} • owner={user.id}",
            reason="MangoMods ticket created",
        )

        created_at = iso_now()
        data = await self.ticket_store.read()
        data.setdefault("open_tickets_by_user", {})
        data.setdefault("ticket_cooldowns", {})
        data.setdefault("tickets_by_channel", {})
        data.setdefault("tickets_completed", 0)

        data["open_tickets_by_user"][str(user.id)] = {
            "channel_id": ticket_channel.id,
            "type": ticket_type,
            "priority": priority,
            "created_at": created_at,
            "claimed_by": None,
        }
        data["ticket_cooldowns"][str(user.id)] = created_at
        data["tickets_by_channel"][str(ticket_channel.id)] = {
            "owner_id": user.id,
            "type": ticket_type,
            "priority": priority,
            "created_at": created_at,
            "closed_at": None,
            "claimed_by": None,
            "locked": False,
            "closed": False,
            "close_reason": None,
            "notes": [],
            "rating": None,
        }
        await self.ticket_store.write(data)

        # Build the ticket opening embed — color matches priority
        type_emoji = TYPE_EMOJIS.get(ticket_type, "🎫")
        priority_color = PRIORITY_COLORS.get(priority, discord.Colour(0xF9A826))
        priority_label = PRIORITY_LABELS.get(priority, priority.title())

        emb = discord.Embed(
            title=f"{type_emoji}  MangoMods — {ticket_type.title()} Ticket",
            description=(
                f"{user.mention} — thanks for reaching out!\n"
                "A staff member will be with you shortly. Please be patient."
            ),
            colour=priority_color,
            timestamp=_now(),
        )

        # Priority + type on the same row
        emb.add_field(name="⚡  Priority", value=priority_label, inline=True)
        emb.add_field(name="📋  Type",     value=f"{type_emoji}  {ticket_type.title()}", inline=True)
        emb.add_field(name="\u200b",       value="\u200b", inline=True)

        # User-provided fields
        for k, v in fields.items():
            emb.add_field(name=k, value=v if v.strip() else "—", inline=False)

        emb.add_field(
            name="🕐  Opened",
            value=f"<t:{int(datetime.fromisoformat(created_at).timestamp())}:F>",
            inline=False,
        )
        emb.set_footer(text=f"MangoMods  •  {self.bot.config.website_url}")

        await ticket_channel.send(
            content=f"{user.mention} | {staff_role.mention}",
            embed=emb,
            view=TicketActionsView(self.bot, locked=False, closed=False),
        )

        await log_action(
            self.bot,
            "Ticket Opened",
            f"Type: **{ticket_type}** | Priority: **{priority_label.strip()}**\n"
            f"User: {user.mention} (`{user.id}`)\n"
            f"Channel: {ticket_channel.mention}",
        )
        await interaction.followup.send(
            f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True
        )

    # ── Ticket button actions ────────────────────────────────────────────────

    async def claim_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Invalid context.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")
        if not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid channel.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not a ticket.")

        if state.get("claimed_by"):
            return await self._ephemeral(
                interaction, f"Already claimed by <@{state['claimed_by']}>."
            )

        await self._set_state(interaction.channel.id, {"claimed_by": interaction.user.id})

        # Keep open_tickets_by_user in sync
        owner_id = int(state.get("owner_id", 0))
        data = await self.ticket_store.read()
        if str(owner_id) in data.get("open_tickets_by_user", {}):
            data["open_tickets_by_user"][str(owner_id)]["claimed_by"] = interaction.user.id
            await self.ticket_store.write(data)

        await interaction.channel.send(
            f"🏷️ Ticket claimed by {interaction.user.mention}."
        )
        await log_action(
            self.bot,
            "Ticket Claimed",
            f"Staff: {interaction.user.mention}\nChannel: {interaction.channel.mention}",
        )

        sa = self.bot.get_cog("StaffActivity")
        if sa:
            await sa.record_ticket_claim(interaction.user.id)

        await interaction.response.send_message("Ticket claimed.", ephemeral=True)

    async def prompt_add_user(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Invalid context.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")
        await interaction.response.send_modal(AddUserModal(self.bot))

    async def add_user_to_ticket(self, interaction: discord.Interaction, user_raw: str):
        if (
            not interaction.guild
            or not isinstance(interaction.user, discord.Member)
            or not isinstance(interaction.channel, discord.TextChannel)
        ):
            return await self._ephemeral(interaction, "Invalid context.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not a ticket.")

        user_id = extract_user_id(user_raw)
        if not user_id:
            return await self._ephemeral(interaction, "Could not parse a user ID or mention.")

        try:
            member = interaction.guild.get_member(user_id) or await interaction.guild.fetch_member(user_id)
        except Exception:
            return await self._ephemeral(interaction, "User not found in this server.")

        await interaction.channel.set_permissions(
            member, view_channel=True, send_messages=True, read_message_history=True
        )
        await interaction.channel.send(f"➕ Added {member.mention} to this ticket.")
        await log_action(
            self.bot,
            "User Added To Ticket",
            f"Staff: {interaction.user.mention}\nAdded: {member.mention}\nChannel: {interaction.channel.mention}",
        )
        await interaction.response.send_message("User added.", ephemeral=True)

    async def prompt_note(self, interaction: discord.Interaction):
        """Called by the Note button in TicketActionsView."""
        if not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Invalid context.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")
        if not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Use this inside a ticket channel.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not a ticket.")

        await interaction.response.send_modal(NoteModal(self.bot, interaction.channel.id))

    async def _post_note(
        self, interaction: discord.Interaction, channel_id: int, note_text: str
    ):
        """Post a staff note embed in the ticket channel and store it in state."""
        if not interaction.guild:
            return

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Channel not found.")

        now = _now()
        emb = discord.Embed(
            title="📝  Staff Note",
            description=note_text,
            colour=discord.Colour(0x9B59B6),  # purple — distinct from normal messages
            timestamp=now,
        )
        emb.set_footer(
            text=f"🔒  Staff Only  •  {interaction.user.display_name}  •  MangoMods"
        )

        await channel.send(embed=emb)

        # Persist the note in ticket state
        data = await self.ticket_store.read()
        entry = data.setdefault("tickets_by_channel", {}).setdefault(str(channel_id), {})
        entry.setdefault("notes", []).append({
            "author_id": interaction.user.id,
            "author_name": interaction.user.display_name,
            "content": note_text,
            "timestamp": now.isoformat(),
        })
        await self.ticket_store.write(data)

        await log_action(
            self.bot,
            "Staff Note Added",
            f"By {interaction.user.mention}\nChannel: {channel.mention}",
        )

        sa = self.bot.get_cog("StaffActivity")
        if sa:
            await sa.record_ticket_note(interaction.user.id)

        await interaction.response.send_message("📝 Note posted.", ephemeral=True)

    async def lock_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not a ticket.")

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await self._ephemeral(interaction, "Staff or ticket owner only.")

        closed = bool(state.get("closed", False))
        owner = interaction.guild.get_member(owner_id)
        if owner:
            await interaction.channel.set_permissions(
                owner, view_channel=True, read_message_history=True, send_messages=False
            )

        await self._set_state(interaction.channel.id, {"locked": True})
        await self._refresh_controls(interaction, interaction.channel, locked=True, closed=closed)
        await log_action(
            self.bot, "Ticket Locked",
            f"By {interaction.user.mention}\nChannel: {interaction.channel.mention}",
        )
        await interaction.response.send_message("🔒 Ticket locked.", ephemeral=True)

    async def unlock_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not a ticket.")

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await self._ephemeral(interaction, "Staff or ticket owner only.")

        closed = bool(state.get("closed", False))
        owner = interaction.guild.get_member(owner_id)
        if owner:
            await interaction.channel.set_permissions(
                owner, view_channel=True, read_message_history=True, send_messages=(not closed)
            )

        await self._set_state(interaction.channel.id, {"locked": False})
        await self._refresh_controls(interaction, interaction.channel, locked=False, closed=closed)
        await log_action(
            self.bot, "Ticket Unlocked",
            f"By {interaction.user.mention}\nChannel: {interaction.channel.mention}",
        )
        await interaction.response.send_message("🔓 Ticket unlocked.", ephemeral=True)

    async def prompt_close_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not a ticket.")

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await self._ephemeral(interaction, "Staff or ticket owner only.")

        await interaction.response.send_modal(CloseReasonModal(self.bot, interaction.channel.id))

    async def reopen_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not a ticket.")

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await self._ephemeral(interaction, "Staff or ticket owner only.")

        owner = interaction.guild.get_member(owner_id)
        if owner:
            await interaction.channel.set_permissions(
                owner, view_channel=True, read_message_history=True, send_messages=True
            )

        if interaction.channel.name.startswith("closed-"):
            try:
                await interaction.channel.edit(
                    name=interaction.channel.name.replace("closed-", "", 1)[:95]
                )
            except Exception:
                pass

        # Restore open ticket mapping
        data = await self.ticket_store.read()
        open_map = data.setdefault("open_tickets_by_user", {})
        if not open_map.get(str(owner_id)):
            open_map[str(owner_id)] = {
                "channel_id": interaction.channel.id,
                "type": state.get("type", "ticket"),
                "priority": state.get("priority", "medium"),
                "created_at": state.get("created_at", iso_now()),
                "claimed_by": state.get("claimed_by"),
            }
            await self.ticket_store.write(data)

        await self._set_state(interaction.channel.id, {"closed": False, "locked": False, "closed_at": None})
        await self._refresh_controls(interaction, interaction.channel, locked=False, closed=False)
        await log_action(
            self.bot, "Ticket Reopened",
            f"By {interaction.user.mention}\nChannel: {interaction.channel.mention}",
        )
        await interaction.response.send_message("✅ Ticket reopened.", ephemeral=True)

    # ── Close ticket (with transcript + rating DM) ───────────────────────────

    async def close_ticket(
        self, interaction: discord.Interaction, channel_id: int, close_reason: str
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Channel not found.", ephemeral=True)

        state = await self._get_state(channel.id)
        if not state:
            return await interaction.followup.send(
                "This channel is not a ticket.", ephemeral=True
            )

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await interaction.followup.send("You can't close this ticket.", ephemeral=True)

        # Fetch message history
        msgs = [m async for m in channel.history(limit=3000, oldest_first=True)]

        created_at_iso = state.get("created_at")
        close_time = _now()
        open_date_str = pretty_dt(created_at_iso) if created_at_iso else "—"
        close_date_str = _fmt_dt(close_time)

        claimed_by_id = state.get("claimed_by")
        claimed_by_str = f"<@{claimed_by_id}>" if claimed_by_id else "Unclaimed"

        # Staff message counts
        staff_role = guild.get_role(self.bot.config.staff_role_id)
        staff_counts: dict[str, int] = {}
        if staff_role:
            staff_ids = {m.id for m in staff_role.members}
            for m in msgs:
                if isinstance(m.author, discord.Member) and m.author.id in staff_ids:
                    n = m.author.display_name
                    staff_counts[n] = staff_counts.get(n, 0) + 1
        staff_count_str = (
            " • ".join(f"{k}: {v}" for k, v in sorted(staff_counts.items(), key=lambda x: -x[1]))
            or "—"
        )

        summary = {
            "Ticket Name":         channel.name,
            "Ticket Author":       f"<@{owner_id}>",
            "Claimed By":          claimed_by_str,
            "Closed By":           str(interaction.user.mention),
            "Open Date":           open_date_str,
            "Close Date":          close_date_str,
            "Ticket Close Reason": close_reason,
            "Staff Message Count": staff_count_str,
        }

        # Build HTML transcript
        notes: list[dict] = state.get("notes") or []
        priority: str = state.get("priority", "medium")

        html_doc = _build_transcript_html(
            guild=guild,
            channel=channel,
            messages=msgs,
            website_url=self.bot.config.website_url,
            summary=summary,
            notes=notes,
            priority=priority,
            rating=state.get("rating"),
        )

        # Post transcript to transcript channel
        transcript_channel = self.bot.get_channel(self.bot.config.transcript_channel_id)
        if transcript_channel is None:
            transcript_channel = await self.bot.fetch_channel(self.bot.config.transcript_channel_id)

        file_bytes = io.BytesIO(html_doc.encode("utf-8"))
        transcript_file = discord.File(
            fp=file_bytes,
            filename=f"transcript-{channel.name}-{channel.id}.html",
        )

        priority_label = PRIORITY_LABELS.get(priority, priority.title())
        priority_color = PRIORITY_COLORS.get(priority, discord.Colour(0xF9A826))

        closed_embed = discord.Embed(
            title="🎫  Ticket Closed",
            colour=priority_color,
            timestamp=close_time,
        )
        closed_embed.add_field(name="Ticket Name",   value=channel.name,               inline=True)
        closed_embed.add_field(name="Priority",      value=priority_label.strip(),      inline=True)
        closed_embed.add_field(name="Type",          value=state.get("type","—").title(), inline=True)
        closed_embed.add_field(name="Ticket Author", value=f"<@{owner_id}>",            inline=True)
        closed_embed.add_field(name="Closed By",     value=interaction.user.mention,    inline=True)
        closed_embed.add_field(name="Claimed By",    value=claimed_by_str,              inline=True)
        closed_embed.add_field(name="Open Date",     value=open_date_str,               inline=True)
        closed_embed.add_field(name="Close Date",    value=close_date_str,              inline=True)
        closed_embed.add_field(name="\u200b",        value="\u200b",                    inline=True)
        closed_embed.add_field(name="Close Reason",        value=close_reason,          inline=False)
        closed_embed.add_field(name="Staff Message Count", value=staff_count_str,       inline=False)
        if notes:
            closed_embed.add_field(name="📝 Staff Notes", value=f"{len(notes)} note(s) — see transcript", inline=False)
        closed_embed.set_footer(text=f"MangoMods  •  {self.bot.config.website_url}")

        transcript_url: Optional[str] = None
        if isinstance(transcript_channel, discord.TextChannel):
            sent = await transcript_channel.send(embed=closed_embed, file=transcript_file)
            if sent.attachments:
                transcript_url = sent.attachments[0].url
            if transcript_url:
                v = discord.ui.View()
                v.add_item(discord.ui.Button(
                    label="📄  Download Transcript",
                    url=transcript_url,
                    style=discord.ButtonStyle.link,
                ))
                await sent.edit(view=v)

        # Update ticket state
        await self._set_state(channel.id, {
            "closed": True,
            "locked": True,
            "close_reason": close_reason,
            "closed_at": close_time.isoformat(),
        })

        # Remove from open ticket lockout (allow user to open a new ticket)
        data = await self.ticket_store.read()
        data.get("open_tickets_by_user", {}).pop(str(owner_id), None)
        data["tickets_completed"] = int(data.get("tickets_completed", 0)) + 1
        await self.ticket_store.write(data)

        # Lock + rename the channel
        try:
            owner = guild.get_member(owner_id)
            if owner:
                await channel.set_permissions(
                    owner, view_channel=True, read_message_history=True, send_messages=False
                )
            if not channel.name.startswith("closed-"):
                await channel.edit(name=f"closed-{channel.name}"[:95])

            await channel.send("🔒 This ticket has been closed and the channel is now locked. Use **♻️ Reopen** to reopen it.")

            # Auto-delete announcement (if configured)
            delay = int(getattr(self.bot.config, "ticket_auto_delete_seconds", 0) or 0)
            if delay > 0:
                e = mango_embed(
                    self.bot,
                    title="🧹  Auto-Delete Scheduled",
                    description=(
                        "This ticket channel will be automatically deleted.\n\n"
                        f"⏳ **Deleting:** <t:{int(close_time.timestamp()) + delay}:R>\n"
                        "Press **♻️ Reopen** before then to cancel."
                    ),
                )
                await channel.send(embed=e)

                async def _delete_later(g: discord.Guild, ch_id: int, secs: int):
                    await asyncio.sleep(secs)
                    ch = g.get_channel(ch_id)
                    if isinstance(ch, discord.TextChannel):
                        try:
                            await ch.delete(reason=f"Auto-delete {secs}s after close")
                        except Exception:
                            pass

                asyncio.create_task(_delete_later(guild, channel.id, delay))
        except Exception:
            pass

        # Refresh buttons to closed state
        await self._refresh_controls(interaction, channel, locked=True, closed=True)

        # Send rating DM to ticket owner
        asyncio.create_task(self._send_rating_dm(guild, owner_id, channel.id))

        await log_action(
            self.bot,
            "Ticket Closed",
            f"Closed by: {interaction.user.mention}\n"
            f"Channel: #{channel.name} (`{channel.id}`)\n"
            f"Priority: **{priority_label.strip()}**\n"
            f"Reason: **{close_reason}**",
        )

        sa = self.bot.get_cog("StaffActivity")
        if sa:
            await sa.record_ticket_close(interaction.user.id)

        await interaction.followup.send(
            "✅ Ticket closed and transcript posted.", ephemeral=True
        )

    # ── Rating system ────────────────────────────────────────────────────────

    async def _send_rating_dm(
        self, guild: discord.Guild, owner_id: int, channel_id: int
    ) -> None:
        """Send a post-close rating request to the ticket owner via DM."""
        try:
            owner = guild.get_member(owner_id) or await guild.fetch_member(owner_id)
            if not owner or owner.bot:
                return

            emb = discord.Embed(
                title="⭐  How was your support experience?",
                description=(
                    "Your MangoMods ticket has been closed.\n\n"
                    "We'd love to know how we did! Tap a rating below.\n"
                    "*Your feedback helps us improve our support quality.*"
                ),
                colour=discord.Colour(0xF9A826),
                timestamp=_now(),
            )
            emb.set_footer(text=f"MangoMods  •  {self.bot.config.website_url}")

            await owner.send(embed=emb, view=TicketRatingView(self.bot, channel_id))
        except Exception:
            pass  # DMs disabled or user left — fail silently

    async def record_rating(self, channel_id: int, rating: int) -> None:
        """Called by TicketRatingView when a user submits a star rating."""
        await self._set_state(channel_id, {"rating": rating})
        await log_action(
            self.bot,
            "Ticket Rated",
            f"Channel: <#{channel_id}>\nRating: **{'⭐' * rating}** ({rating}/5)",
        )

    # ── /ticket note ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="note",
        description="Add a private staff note to this ticket channel (staff only).",
    )
    async def note(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")
        if not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Use this inside a ticket channel.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not a ticket.")

        await interaction.response.send_modal(NoteModal(self.bot, interaction.channel.id))

    # ── /ticket stats ────────────────────────────────────────────────────────

    @app_commands.command(
        name="stats",
        description="View ticket statistics (staff only).",
    )
    async def stats(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        data = await self.ticket_store.read()
        by_channel: dict[str, Any] = data.get("tickets_by_channel", {})
        open_map: dict[str, Any] = data.get("open_tickets_by_user", {})

        total_opened  = len(by_channel)
        total_closed  = sum(1 for t in by_channel.values() if t.get("closed"))
        currently_open = len(open_map)

        # Average close time
        close_times: list[float] = []
        for t in by_channel.values():
            if t.get("closed") and t.get("created_at") and t.get("closed_at"):
                try:
                    opened  = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
                    closed_dt = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
                    diff = (closed_dt - opened).total_seconds()
                    if diff > 0:
                        close_times.append(diff)
                except Exception:
                    pass

        avg_close = sum(close_times) / len(close_times) if close_times else None

        # Average rating
        ratings = [t["rating"] for t in by_channel.values() if t.get("rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else None

        # Top staff by claims
        claim_counts: dict[int, int] = {}
        for t in by_channel.values():
            cby = t.get("claimed_by")
            if cby:
                uid = int(cby)
                claim_counts[uid] = claim_counts.get(uid, 0) + 1

        top_claimers = sorted(claim_counts.items(), key=lambda x: -x[1])[:5]

        # Breakdown by type
        type_counts: dict[str, int] = {}
        for t in by_channel.values():
            tt = t.get("type", "unknown")
            type_counts[tt] = type_counts.get(tt, 0) + 1

        emb = discord.Embed(
            title="📊  MangoMods — Ticket Statistics",
            colour=discord.Colour(0xF9A826),
            timestamp=_now(),
        )

        emb.add_field(name="📬  Total Opened",    value=f"**{total_opened}**",    inline=True)
        emb.add_field(name="✅  Total Closed",    value=f"**{total_closed}**",    inline=True)
        emb.add_field(name="📂  Currently Open",  value=f"**{currently_open}**",  inline=True)

        emb.add_field(
            name="⏱️  Avg Close Time",
            value=f"**{_fmt_duration(avg_close)}**" if avg_close else "**—**",
            inline=True,
        )
        emb.add_field(
            name="⭐  Avg Rating",
            value=f"**{avg_rating:.1f} / 5.0**" if avg_rating else "**—**",
            inline=True,
        )
        emb.add_field(
            name="🗳️  Total Ratings",
            value=f"**{len(ratings)}**",
            inline=True,
        )

        if type_counts:
            type_lines = []
            for tt, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                emoji = TYPE_EMOJIS.get(tt, "🎫")
                type_lines.append(f"{emoji} {tt.title()}: **{count}**")
            emb.add_field(
                name="📋  Breakdown by Type",
                value="\n".join(type_lines),
                inline=False,
            )

        if top_claimers:
            guild = interaction.guild
            lines = []
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, (uid, count) in enumerate(top_claimers):
                member = guild.get_member(uid)
                name = member.display_name if member else f"<@{uid}>"
                medal = medals[i] if i < len(medals) else f"{i+1}."
                lines.append(f"{medal}  {name} — **{count}** claim{'s' if count != 1 else ''}")
            emb.add_field(
                name="🏆  Top Staff by Claims",
                value="\n".join(lines),
                inline=False,
            )

        emb.set_footer(text="MangoMods  •  All Time Statistics")
        await interaction.followup.send(embed=emb, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
