from __future__ import annotations

import asyncio
import io
import html
from datetime import datetime, timezone
from typing import Dict, Optional, Any

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed
from mangomods_bot.utils.log import log_action
from mangomods_bot.utils.misc import iso_now, pretty_dt, sanitize_channel_name, extract_user_id
from mangomods_bot.views.ticket_panel import TicketPanelView
from mangomods_bot.views.ticket_actions import TicketActionsView


def _fmt_ticketking_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")


def _build_ticketking_html(
    *,
    guild: discord.Guild,
    channel: discord.TextChannel,
    messages: list[discord.Message],
    website_url: str,
    summary: dict[str, str],
) -> str:
    css = """
    :root{
      --bg:#0b0f14; --panel:#0f1623; --panel2:#101a2a; --border:#263043;
      --text:#e6edf3; --muted:rgba(230,237,243,.75); --accent:#f9a826;
    }
    body{margin:0;background:var(--bg);color:var(--text);
         font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;}
    a{color:#7cc4ff;text-decoration:none;}
    .wrap{max-width:1000px;margin:0 auto;padding:22px 14px 40px;}
    .card{border:1px solid var(--border);background:var(--panel);border-radius:14px;overflow:hidden;
          box-shadow:0 10px 40px rgba(0,0,0,.35);}
    .cardHead{padding:14px 16px;display:flex;justify-content:space-between;align-items:flex-start;
              background:rgba(255,255,255,.02);border-bottom:1px solid var(--border);}
    .cardHead h2{margin:0;font-size:15px;font-weight:800;}
    .meta{color:var(--muted);font-size:12px;margin-top:4px;}
    .grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;padding:14px 16px;background:var(--panel2);}
    .kv{border:1px solid rgba(38,48,67,.9);background:rgba(0,0,0,.15);border-radius:12px;padding:10px 10px;min-height:58px;}
    .k{font-size:12px;color:var(--muted);font-weight:700;}
    .v{margin-top:4px;font-size:13px;font-weight:700;word-break:break-word;}
    .msgList{margin-top:16px;border:1px solid var(--border);border-radius:14px;overflow:hidden;}
    .msg{display:flex;gap:12px;padding:12px 12px;border-bottom:1px solid #1c2533;background:rgba(255,255,255,.01);}
    .msg:last-child{border-bottom:none;}
    .av{width:40px;height:40px;border-radius:999px;flex:0 0 auto;}
    .who{font-weight:800;font-size:13px;}
    .when{margin-left:8px;font-size:12px;color:var(--muted);}
    .content{margin-top:4px;white-space:pre-wrap;line-height:1.35;font-size:13px;color:rgba(230,237,243,.92);}
    .attachments{margin-top:6px;font-size:12px;color:var(--muted);}
    .badge{display:inline-block;padding:2px 8px;border:1px solid var(--border);
           border-radius:999px;font-size:11px;color:var(--muted);margin-left:8px;}
    """

    def kv(k: str, v: str) -> str:
        return f"""
        <div class="kv">
          <div class="k">{html.escape(k)}</div>
          <div class="v">{html.escape(v or "—")}</div>
        </div>
        """

    summary_boxes = "".join(
        [
            kv("Ticket Name", summary.get("Ticket Name", "")),
            kv("Ticket Author", summary.get("Ticket Author", "")),
            kv("Claimed By", summary.get("Claimed By", "")),
            kv("Closed By", summary.get("Closed By", "")),
            kv("Open Date", summary.get("Open Date", "")),
            kv("Close Date", summary.get("Close Date", "")),
            kv("Ticket Close Reason", summary.get("Ticket Close Reason", "")),
            kv("Staff Message Count", summary.get("Staff Message Count", "")),
            kv("Server", guild.name),
        ]
    )

    rows = []
    for m in messages:
        author = m.author
        av = getattr(author.display_avatar, "url", "")
        name = getattr(author, "display_name", str(author))
        ts = _fmt_ticketking_dt(m.created_at)

        content = m.content or ""
        if not content and m.embeds:
            parts = []
            for e in m.embeds:
                t = e.title or ""
                d = e.description or ""
                if t or d:
                    parts.append(f"[EMBED] {t}\n{d}".strip())
            content = "\n\n".join(parts)

        safe_content = html.escape(content)
        attach_lines = [f'📎 <a href="{html.escape(a.url)}">{html.escape(a.filename)}</a>' for a in m.attachments]
        attach_html = f'<div class="attachments">{"<br/>".join(attach_lines)}</div>' if attach_lines else ""
        bot_badge = '<span class="badge">BOT</span>' if author.bot else ""

        rows.append(
            f"""
            <div class="msg">
              <img class="av" src="{html.escape(av)}" alt="avatar"/>
              <div style="flex:1 1 auto;">
                <div><span class="who">{html.escape(name)}</span>{bot_badge}<span class="when">{html.escape(ts)}</span></div>
                <div class="content">{safe_content}</div>
                {attach_html}
              </div>
            </div>
            """
        )

    exported = _fmt_ticketking_dt(datetime.now(timezone.utc))

    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{html.escape(summary.get("Ticket Name","MangoMods Ticket Transcript"))}</title>
      <style>{css}</style>
    </head>
    <body>
      <div class="wrap">
        <div class="card">
          <div class="cardHead">
            <div>
              <h2>Ticket Closed</h2>
              <div class="meta">Channel: #{html.escape(channel.name)} • Exported: {html.escape(exported)} • Website: <a href="{html.escape(website_url)}">{html.escape(website_url)}</a></div>
            </div>
          </div>
          <div class="grid">{summary_boxes}</div>
        </div>

        <div class="msgList">
          {''.join(rows)}
        </div>
      </div>
    </body>
    </html>
    """


class AddUserModal(discord.ui.Modal, title="Add User To Ticket"):
    user_input = discord.ui.TextInput(
        label="User ID or mention",
        placeholder="Paste a user ID or mention like @User",
        max_length=100,
    )

    def __init__(self, bot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        cog = self.bot.get_cog("ticket") or self.bot.get_cog("Tickets")
        if not cog:
            return await interaction.response.send_message("Ticket system not loaded.", ephemeral=True)
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
            return await interaction.response.send_message("Ticket system not loaded.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        await cog.close_ticket(interaction, self.channel_id, str(self.reason).strip() or "No Answer")


class Tickets(commands.GroupCog, name="ticket"):
    """
    /ticket panel (staff) -> posts persistent ticket panel.
    Ticket opening is done via buttons + modals.
    """
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        self.ticket_store = JSONStore(
            "/data/tickets.json",
            {
                "open_tickets_by_user": {},
                "ticket_cooldowns": {},
                "tickets_completed": 0,
                "tickets_by_channel": {},  # NEW: per-channel state
            },
        )
        self.panel_store = JSONStore(
            "/data/panels.json",
            {
                "ticket_panel": None,
                "status_panel": None,
            },
        )

        self._panel_lock = asyncio.Lock()

    # -----------------------
    # Helpers
    # -----------------------
    async def _ephemeral(self, interaction: discord.Interaction, content: str) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True)
        else:
            await interaction.response.send_message(content, ephemeral=True)

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

    async def _get_open_ticket_channel(self, guild: discord.Guild, user_id: int) -> Optional[discord.TextChannel]:
        data = await self.ticket_store.read()
        meta = data.get("open_tickets_by_user", {}).get(str(user_id))
        if not meta:
            return None

        ch = guild.get_channel(int(meta.get("channel_id", 0)))
        if isinstance(ch, discord.TextChannel):
            return ch

        # stale cleanup
        try:
            data.get("open_tickets_by_user", {}).pop(str(user_id), None)
            await self.ticket_store.write(data)
        except Exception:
            pass
        return None

    async def _cooldown_ok(self, user_id: int) -> tuple[bool, str]:
        secs = int(self.bot.config.ticket_cooldown_seconds or 0)
        if secs <= 0:
            return True, ""

        data = await self.ticket_store.read()
        cooldowns = data.get("ticket_cooldowns", {})
        last_iso = cooldowns.get(str(user_id))
        if not last_iso:
            return True, ""

        try:
            last = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = (now - last).total_seconds()
            if delta < secs:
                remain = int(secs - delta)
                return False, f"Please wait **{remain}s** before opening another ticket."
        except Exception:
            return True, ""

        return True, ""

    async def _get_or_create_tickets_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        if self.bot.config.tickets_category_id:
            cat = guild.get_channel(self.bot.config.tickets_category_id)
            if isinstance(cat, discord.CategoryChannel):
                return cat

        for c in guild.categories:
            if c.name.lower() == "tickets":
                return c

        return await guild.create_category("Tickets", reason="MangoMods ticket system category")

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

    async def _find_actions_message(self, channel: discord.TextChannel) -> Optional[discord.Message]:
        """
        Finds the most recent bot message in the channel that has our ticket action buttons.
        Used when close happens via modal (no interaction.message to edit).
        """
        if not self.bot.user:
            return None
        async for m in channel.history(limit=30, oldest_first=False):
            if m.author.id != self.bot.user.id:
                continue
            if not m.components:
                continue
            # crude check: one of our custom ids
            has_any = False
            for row in m.components:
                for c in getattr(row, "children", []):
                    cid = getattr(c, "custom_id", "")
                    if cid and cid.startswith("mangomods:ticket:"):
                        has_any = True
                        break
                if has_any:
                    break
            if has_any:
                return m
        return None

    async def _refresh_controls(self, interaction: discord.Interaction, channel: discord.TextChannel, locked: bool, closed: bool) -> None:
        """
        Update the control message so the button states match the new ticket state.
        """
        try:
            if interaction.message:
                await interaction.message.edit(view=TicketActionsView(self.bot, locked=locked, closed=closed))
                return
        except Exception:
            pass

        try:
            msg = await self._find_actions_message(channel)
            if msg:
                await msg.edit(view=TicketActionsView(self.bot, locked=locked, closed=closed))
        except Exception:
            pass

    def _build_panel_embed(self) -> discord.Embed:
        emb = mango_embed(
            self.bot,
            title="🍋 MangoMods — Tickets",
            description=(
                "Open a ticket using the buttons below.\n\n"
                f"Website: **{self.bot.config.website_url}**\n"
                "Please provide accurate info so staff can help quickly."
            ),
        )
        emb.add_field(name="Ticket Types", value="🟩 Purchase • 🟦 Support • ⬜ General Questions", inline=False)
        emb.set_footer(text="MangoMods • Ticket System")
        return emb

    # -----------------------
    # /ticket panel (staff)
    # -----------------------
    @app_commands.command(name="panel", description="Post/update the MangoMods ticket panel (persistent).")
    @app_commands.describe(channel="Optional channel to post the panel in (defaults to current channel).")
    async def panel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not interaction.guild:
            return await self._ephemeral(interaction, "Use this in a server.")

        if not isinstance(interaction.user, discord.Member) or self.bot.config.staff_role_id not in [r.id for r in interaction.user.roles]:
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
                    old_channel_id = int(existing["channel_id"])
                    old_message_id = int(existing["message_id"])

                    old_channel = interaction.guild.get_channel(old_channel_id)
                    if old_channel is None:
                        fetched = await self.bot.fetch_channel(old_channel_id)
                        old_channel = fetched if isinstance(fetched, discord.TextChannel) else None

                    if isinstance(old_channel, discord.TextChannel):
                        old_msg = await old_channel.fetch_message(old_message_id)

                        if old_channel.id != target.id:
                            try:
                                await old_msg.delete()
                            except Exception:
                                pass

                            new_msg = await target.send(embed=emb, view=view)
                            panels["ticket_panel"] = {"channel_id": target.id, "message_id": new_msg.id}
                            await self.panel_store.write(panels)

                            await log_action(self.bot, "Ticket Panel Moved", f"Moved by {interaction.user.mention} to {target.mention}")
                            return await interaction.followup.send("Ticket panel moved/posted.", ephemeral=True)

                        await old_msg.edit(embed=emb, view=view)
                        await log_action(self.bot, "Ticket Panel Updated", f"Updated by {interaction.user.mention} in {target.mention}")
                        return await interaction.followup.send("Ticket panel updated.", ephemeral=True)

                except Exception:
                    pass

            msg = await target.send(embed=emb, view=view)
            panels["ticket_panel"] = {"channel_id": target.id, "message_id": msg.id}
            await self.panel_store.write(panels)

            await log_action(self.bot, "Ticket Panel Posted", f"Posted by {interaction.user.mention} in {target.mention}")
            await interaction.followup.send("Ticket panel posted.", ephemeral=True)

    # -----------------------
    # Ticket creation
    # -----------------------
    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str, fields: Dict[str, str]):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Tickets can only be opened in a server.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        user = interaction.user

        existing = await self._get_open_ticket_channel(guild, user.id)
        if existing:
            return await interaction.followup.send(f"You already have an open ticket: {existing.mention}", ephemeral=True)

        ok, msg = await self._cooldown_ok(user.id)
        if not ok:
            return await interaction.followup.send(msg, ephemeral=True)

        category = await self._get_or_create_tickets_category(guild)

        staff_role = self._staff_role(guild)
        if staff_role is None:
            return await interaction.followup.send("STAFF_ROLE_ID is invalid (role not found).", ephemeral=True)

        prefix = {"purchase": "purchase", "support": "support", "general": "general"}.get(ticket_type, "ticket")
        base_name = f"{prefix}-{sanitize_channel_name(user.display_name)}"
        channel_name = await self._unique_channel_name(guild, base_name)

        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        bot_member = guild.me or (guild.get_member(self.bot.user.id) if self.bot.user else None)  # type: ignore[union-attr]
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"MangoMods ticket • type={ticket_type} • owner={user.id}",
            reason="MangoMods ticket created",
        )

        # Save ticket meta
        data = await self.ticket_store.read()
        data.setdefault("open_tickets_by_user", {})
        data.setdefault("ticket_cooldowns", {})
        data.setdefault("tickets_by_channel", {})
        data.setdefault("tickets_completed", 0)

        created_at = iso_now()
        data["open_tickets_by_user"][str(user.id)] = {
            "channel_id": ticket_channel.id,
            "type": ticket_type,
            "created_at": created_at,
            "claimed_by": None,
        }
        data["ticket_cooldowns"][str(user.id)] = iso_now()

        data["tickets_by_channel"][str(ticket_channel.id)] = {
            "owner_id": user.id,
            "type": ticket_type,
            "created_at": created_at,
            "claimed_by": None,
            "locked": False,
            "closed": False,
            "close_reason": None,
        }

        await self.ticket_store.write(data)

        # Ticket summary embed + actions
        emb = mango_embed(
            self.bot,
            title=f"🎫 MangoMods — {ticket_type.title()} Ticket",
            description=f"{user.mention} thanks — a staff member will be with you shortly.",
        )
        for k, v in fields.items():
            emb.add_field(name=k, value=v if v.strip() else "—", inline=False)

        emb.add_field(name="Opened", value=pretty_dt(created_at), inline=False)
        emb.set_footer(text=f"MangoMods • {self.bot.config.website_url}")

        await ticket_channel.send(
            content=f"{user.mention} | {staff_role.mention}",
            embed=emb,
            view=TicketActionsView(self.bot, locked=False, closed=False),
        )

        await log_action(
            self.bot,
            "Ticket Opened",
            f"Type: **{ticket_type}**\nUser: {user.mention} (`{user.id}`)\nChannel: {ticket_channel.mention}",
        )

        await interaction.followup.send(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

    # -----------------------
    # Ticket button actions
    # -----------------------
    async def claim_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not recognized as a ticket.")

        if state.get("claimed_by"):
            return await self._ephemeral(interaction, f"Already claimed by <@{state['claimed_by']}>.")

        await self._set_state(interaction.channel.id, {"claimed_by": interaction.user.id})

        # also update open map if this is still the user's active open ticket
        owner_id = int(state.get("owner_id", 0))
        data = await self.ticket_store.read()
        if str(owner_id) in data.get("open_tickets_by_user", {}):
            data["open_tickets_by_user"][str(owner_id)]["claimed_by"] = interaction.user.id
            await self.ticket_store.write(data)

        await interaction.channel.send(f"✅ Ticket claimed by {interaction.user.mention}.")
        await log_action(self.bot, "Ticket Claimed", f"Staff: {interaction.user.mention}\nChannel: {interaction.channel.mention}")
        await interaction.response.send_message("Ticket claimed.", ephemeral=True)

    async def prompt_add_user(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Invalid context.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")
        await interaction.response.send_modal(AddUserModal(self.bot))

    async def add_user_to_ticket(self, interaction: discord.Interaction, user_raw: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")
        if not await self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not recognized as a ticket.")

        user_id = extract_user_id(user_raw)
        if not user_id:
            return await self._ephemeral(interaction, "Could not parse a user ID/mention.")

        try:
            member = interaction.guild.get_member(user_id) or await interaction.guild.fetch_member(user_id)
        except Exception:
            return await self._ephemeral(interaction, "User not found in this server.")

        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.channel.send(f"➕ Added {member.mention} to this ticket.")

        await log_action(
            self.bot,
            "User Added To Ticket",
            f"Staff: {interaction.user.mention}\nAdded: {member.mention}\nChannel: {interaction.channel.mention}",
        )
        await interaction.response.send_message("User added.", ephemeral=True)

    async def lock_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not recognized as a ticket.")

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await self._ephemeral(interaction, "Staff or ticket owner only.")

        closed = bool(state.get("closed", False))
        owner = interaction.guild.get_member(owner_id)
        if owner:
            # locked: owner cannot talk (staff can)
            await interaction.channel.set_permissions(owner, view_channel=True, read_message_history=True, send_messages=False)

        await self._set_state(interaction.channel.id, {"locked": True})
        await self._refresh_controls(interaction, interaction.channel, locked=True, closed=closed)

        await log_action(self.bot, "Ticket Locked", f"By {interaction.user.mention}\nChannel: {interaction.channel.mention}")
        await interaction.response.send_message("🔒 Ticket locked.", ephemeral=True)

    async def unlock_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not recognized as a ticket.")

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await self._ephemeral(interaction, "Staff or ticket owner only.")

        closed = bool(state.get("closed", False))
        owner = interaction.guild.get_member(owner_id)
        if owner:
            # unlocked: owner can talk only if not closed
            await interaction.channel.set_permissions(owner, view_channel=True, read_message_history=True, send_messages=(not closed))

        await self._set_state(interaction.channel.id, {"locked": False})
        await self._refresh_controls(interaction, interaction.channel, locked=False, closed=closed)

        await log_action(self.bot, "Ticket Unlocked", f"By {interaction.user.mention}\nChannel: {interaction.channel.mention}")
        await interaction.response.send_message("🔓 Ticket unlocked.", ephemeral=True)

    async def prompt_close_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not recognized as a ticket.")

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await self._ephemeral(interaction, "Staff or ticket owner only.")

        await interaction.response.send_modal(CloseReasonModal(self.bot, interaction.channel.id))

    async def reopen_ticket(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await self._ephemeral(interaction, "Invalid context.")

        state = await self._get_state(interaction.channel.id)
        if not state:
            return await self._ephemeral(interaction, "This channel is not recognized as a ticket.")

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await self._ephemeral(interaction, "Staff or ticket owner only.")

        # restore perms
        owner = interaction.guild.get_member(owner_id)
        if owner:
            await interaction.channel.set_permissions(owner, view_channel=True, read_message_history=True, send_messages=True)

        # rename back if closed-
        if interaction.channel.name.startswith("closed-"):
            try:
                await interaction.channel.edit(name=interaction.channel.name.replace("closed-", "", 1)[:95])
            except Exception:
                pass

        # restore "open ticket per user" mapping if they don't have another open ticket
        data = await self.ticket_store.read()
        open_map = data.setdefault("open_tickets_by_user", {})
        current = open_map.get(str(owner_id))
        if not current:
            open_map[str(owner_id)] = {
                "channel_id": interaction.channel.id,
                "type": state.get("type", "ticket"),
                "created_at": state.get("created_at", iso_now()),
                "claimed_by": state.get("claimed_by"),
            }
            await self.ticket_store.write(data)

        await self._set_state(interaction.channel.id, {"closed": False, "locked": False})
        await self._refresh_controls(interaction, interaction.channel, locked=False, closed=False)

        await log_action(self.bot, "Ticket Reopened", f"By {interaction.user.mention}\nChannel: {interaction.channel.mention}")
        await interaction.response.send_message("✅ Ticket reopened.", ephemeral=True)

    # -----------------------
    # Close (transcript + mark closed)
    # -----------------------
    async def close_ticket(self, interaction: discord.Interaction, channel_id: int, close_reason: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Channel not found.", ephemeral=True)

        state = await self._get_state(channel.id)
        if not state:
            return await interaction.followup.send("This channel is not recognized as a ticket.", ephemeral=True)

        owner_id = int(state.get("owner_id", 0))
        if not await self._is_owner_or_staff(interaction, owner_id):
            return await interaction.followup.send("You can't close this ticket.", ephemeral=True)

        # Fetch messages (cap so it doesn't hang forever)
        MAX_TRANSCRIPT_MESSAGES = 3000
        msgs = [m async for m in channel.history(limit=MAX_TRANSCRIPT_MESSAGES, oldest_first=True)]

        created_at_iso = state.get("created_at")
        open_date_str = pretty_dt(created_at_iso) if created_at_iso else "—"
        close_date_str = _fmt_ticketking_dt(datetime.now(timezone.utc))

        claimed_by_id = state.get("claimed_by")
        claimed_by = f"<@{claimed_by_id}>" if claimed_by_id else "—"

        # Staff message counts
        staff_role = guild.get_role(self.bot.config.staff_role_id)
        staff_counts: dict[str, int] = {}
        if staff_role:
            staff_ids = {m.id for m in staff_role.members}
            for m in msgs:
                if isinstance(m.author, discord.Member) and m.author.id in staff_ids:
                    staff_counts[m.author.display_name] = staff_counts.get(m.author.display_name, 0) + 1
        staff_count_lines = " • ".join([f"{k}: {v}" for k, v in sorted(staff_counts.items(), key=lambda x: -x[1])]) or "—"

        summary = {
            "Ticket Name": channel.name,
            "Ticket Author": f"<@{owner_id}>",
            "Claimed By": claimed_by,
            "Closed By": interaction.user.mention,
            "Open Date": open_date_str,
            "Close Date": close_date_str,
            "Ticket Close Reason": close_reason,
            "Staff Message Count": staff_count_lines,
        }

        html_doc = _build_ticketking_html(
            guild=guild,
            channel=channel,
            messages=msgs,
            website_url=self.bot.config.website_url,
            summary=summary,
        )

        transcript_channel = self.bot.get_channel(self.bot.config.transcript_channel_id)
        if transcript_channel is None:
            transcript_channel = await self.bot.fetch_channel(self.bot.config.transcript_channel_id)

        file_bytes = io.BytesIO(html_doc.encode("utf-8"))
        transcript_file = discord.File(fp=file_bytes, filename=f"transcript-{channel.name}-{channel.id}.html")

        # Ticket Closed embed + transcript button
        ticket_closed_embed = mango_embed(self.bot, title="Ticket Closed", description=None)
        ticket_closed_embed.add_field(name="Ticket Name", value=channel.name, inline=True)
        ticket_closed_embed.add_field(name="Ticket Author", value=f"<@{owner_id}>", inline=True)
        ticket_closed_embed.add_field(name="Closed By", value=interaction.user.mention, inline=True)
        ticket_closed_embed.add_field(name="Claimed By", value=claimed_by, inline=True)
        ticket_closed_embed.add_field(name="Open Date", value=open_date_str, inline=True)
        ticket_closed_embed.add_field(name="Close Date", value=close_date_str, inline=True)
        ticket_closed_embed.add_field(name="Ticket Close Reason", value=close_reason, inline=False)
        ticket_closed_embed.add_field(name="Staff Message Count", value=staff_count_lines, inline=False)

        transcript_url: Optional[str] = None
        if isinstance(transcript_channel, discord.TextChannel):
            sent = await transcript_channel.send(embed=ticket_closed_embed, file=transcript_file)
            if sent.attachments:
                transcript_url = sent.attachments[0].url
            if transcript_url:
                v = discord.ui.View()
                v.add_item(discord.ui.Button(label="Download Transcript", url=transcript_url, style=discord.ButtonStyle.link))
                await sent.edit(view=v)

        # Mark closed + locked in state
        await self._set_state(channel.id, {"closed": True, "locked": True, "close_reason": close_reason})

        # Remove from open ticket lockout so user can open a new ticket
        data = await self.ticket_store.read()
        data.get("open_tickets_by_user", {}).pop(str(owner_id), None)
        data["tickets_completed"] = int(data.get("tickets_completed", 0)) + 1
        await self.ticket_store.write(data)

        # Lock perms + rename closed-
        try:
            owner = guild.get_member(owner_id)
            if owner:
                await channel.set_permissions(owner, view_channel=True, read_message_history=True, send_messages=False)

            if not channel.name.startswith("closed-"):
                await channel.edit(name=f"closed-{channel.name}"[:95])

            await channel.send("🔒 Ticket closed. This channel is now locked. Use **Reopen** to open it again.")

            # After locking/renaming, announce auto-delete (if enabled)
            delay = int(getattr(self.bot.config, "ticket_auto_delete_seconds", 0) or 0)
            if delay > 0:
                e = mango_embed(
                    self.bot,
                    title="🧹 Auto Delete Scheduled",
                    description=(
                        "This ticket has been closed and will be deleted automatically.\n\n"
                        f"⏳ **Time remaining:** <t:{int(datetime.now(timezone.utc).timestamp()) + delay}:R>\n"
                        "If you need to keep it open, press **Reopen**."
                    ),
                )
                e.set_footer(text=f"MangoMods • {self.bot.config.website_url}")
                await channel.send(embed=e)

                # Actually schedule deletion (only if you want it)
                async def _delete_later(g: discord.Guild, ch_id: int, seconds: int):
                    await asyncio.sleep(seconds)
                    ch = g.get_channel(ch_id)
                    if isinstance(ch, discord.TextChannel):
                        try:
                            await ch.delete(reason=f"Auto-delete after close ({seconds}s)")
                        except Exception:
                            pass

                asyncio.create_task(_delete_later(guild, channel.id, delay))

        except Exception:
            pass

        # Refresh control buttons
        await self._refresh_controls(interaction, channel, locked=True, closed=True)

        await log_action(
            self.bot,
            "Ticket Closed",
            f"Closed by: {interaction.user.mention}\nChannel: #{channel.name} (`{channel.id}`)\nReason: **{close_reason}**",
        )

        await interaction.followup.send("Ticket closed and transcript posted.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))