from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed, context_color
from mangomods_bot.utils.log import log_action


def _int_env(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)) or str(default))
    except Exception:
        return default


# ──────────────────────────────────────────────────────────────────────────────
# Persistent enter button view
# ──────────────────────────────────────────────────────────────────────────────

class GiveawayEnterView(discord.ui.View):
    """
    Persistent view — survives bot restarts.
    custom_id encodes the giveaway message ID so we always know which
    giveaway this button belongs to regardless of what's in memory.
    """

    def __init__(self, bot: commands.Bot, message_id: int):
        super().__init__(timeout=None)
        self.bot        = bot
        self.message_id = message_id
        # Dynamic custom_id so Discord can route this back after a restart
        self._enter_btn.custom_id = f"mangomods:giveaway:enter:{message_id}"

    @discord.ui.button(
        label="🎉  Enter Giveaway",
        style=discord.ButtonStyle.success,
        custom_id="mangomods:giveaway:enter:placeholder",  # overwritten in __init__
    )
    async def _enter_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self.bot.get_cog("Giveaways")
        if not cog:
            return await interaction.response.send_message(
                "Giveaway system not loaded.", ephemeral=True
            )
        await cog.handle_enter(interaction, self.message_id)


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────

class Giveaways(commands.Cog):
    """
    /giveaway start   — start a giveaway
    /giveaway end     — end early and pick winner(s) now
    /giveaway reroll  — reroll winner(s) for a finished giveaway
    /giveaway list    — list active giveaways in this server

    Giveaways auto-end via a 60s background task.
    All state lives in /data/giveaways.json.

    Data schema per giveaway (keyed by str(message_id)):
    {
        "message_id":   int,
        "channel_id":   int,
        "guild_id":     int,
        "prize":        str,
        "winners":      int,          # how many winners to pick
        "host_id":      int,
        "ends_at":      str,          # ISO timestamp
        "ended":        bool,
        "entries":      [int, ...],   # list of user IDs
        "winner_ids":   [int, ...],   # populated after end
        "required_role_id": int|null, # optional entry requirement
    }
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot   = bot
        self.store = JSONStore("/data/giveaways.json", {"giveaways": {}})
        self._lock = asyncio.Lock()

    async def cog_load(self) -> None:
        self.check_ended.start()

    async def cog_unload(self) -> None:
        self.check_ended.cancel()

    # ── Permission check ──────────────────────────────────────────────────────

    def _is_staff(self, member: discord.Member) -> bool:
        return any(
            r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id}
            for r in member.roles
        )

    # ── Embed builder ─────────────────────────────────────────────────────────

    def _build_embed(
        self,
        *,
        prize: str,
        host: discord.Member | discord.User,
        ends_at: datetime,
        winner_count: int,
        entries: int,
        ended: bool = False,
        winner_mentions: list[str] | None = None,
        required_role: discord.Role | None = None,
    ) -> discord.Embed:

        color  = "muted" if ended else "premium"
        status = "🏁  Ended" if ended else "🎉  Active"

        emb = mango_embed(self.bot, color=color, footer="Giveaways")
        emb.title = f"🎁  {prize}"

        if ended and winner_mentions:
            emb.description = (
                f"**Winner{'s' if len(winner_mentions) > 1 else ''}:** "
                + ", ".join(winner_mentions)
            )
        elif ended:
            emb.description = "This giveaway has ended. No valid entries were found."
        else:
            emb.description = (
                f"Click **Enter Giveaway** below to enter!\n"
                + (f"*Requires: {required_role.mention}*" if required_role else "")
            )

        emb.add_field(name="🏆  Winners",  value=str(winner_count),              inline=True)
        emb.add_field(name="🎟️  Entries",  value=str(entries),                   inline=True)
        emb.add_field(name="📊  Status",   value=status,                         inline=True)
        emb.add_field(name="👤  Hosted by", value=host.mention,                  inline=True)

        if not ended:
            emb.add_field(
                name="⏰  Ends",
                value=f"<t:{int(ends_at.timestamp())}:R> (<t:{int(ends_at.timestamp())}:F>)",
                inline=True,
            )
        else:
            emb.add_field(
                name="⏰  Ended",
                value=f"<t:{int(ends_at.timestamp())}:R>",
                inline=True,
            )

        return emb

    # ── Handle entry ──────────────────────────────────────────────────────────

    async def handle_enter(self, interaction: discord.Interaction, message_id: int) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        async with self._lock:
            data = await self.store.read()
            key  = str(message_id)
            gw   = data.get("giveaways", {}).get(key)

            if not gw:
                return await interaction.response.send_message(
                    "This giveaway no longer exists.", ephemeral=True
                )
            if gw.get("ended"):
                return await interaction.response.send_message(
                    "This giveaway has already ended.", ephemeral=True
                )

            # Required role check
            req_role_id = gw.get("required_role_id")
            if req_role_id:
                if not any(r.id == req_role_id for r in interaction.user.roles):
                    role = interaction.guild.get_role(req_role_id)
                    req_name = role.mention if role else f"<@&{req_role_id}>"
                    return await interaction.response.send_message(
                        f"You need {req_name} to enter this giveaway.", ephemeral=True
                    )

            uid      = interaction.user.id
            entries  = gw.setdefault("entries", [])
            toggled  = False

            if uid in entries:
                entries.remove(uid)
                toggled = False   # withdrew
            else:
                entries.append(uid)
                toggled = True    # entered

            await self.store.write(data)

        # Update embed entry count
        try:
            ch  = interaction.guild.get_channel(gw["channel_id"])
            msg = await ch.fetch_message(message_id)
            host = interaction.guild.get_member(gw["host_id"]) or await self.bot.fetch_user(gw["host_id"])
            ends_at = datetime.fromisoformat(gw["ends_at"])
            req_role = interaction.guild.get_role(req_role_id) if req_role_id else None
            new_emb = self._build_embed(
                prize          = gw["prize"],
                host           = host,
                ends_at        = ends_at,
                winner_count   = gw["winners"],
                entries        = len(entries),
                required_role  = req_role,
            )
            await msg.edit(embed=new_emb)
        except Exception:
            pass

        if toggled:
            await interaction.response.send_message(
                f"✅ You've entered the **{gw['prize']}** giveaway! Good luck!", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"↩️ You've withdrawn from the **{gw['prize']}** giveaway.", ephemeral=True
            )

    # ── Pick winners ──────────────────────────────────────────────────────────

    async def _end_giveaway(self, key: str, data: dict, *, early: bool = False) -> list[int]:
        gw      = data["giveaways"][key]
        entries = gw.get("entries", [])
        count   = int(gw.get("winners", 1))

        winners = random.sample(entries, min(count, len(entries))) if entries else []

        gw["ended"]      = True
        gw["winner_ids"] = winners
        await self.store.write(data)

        # Update giveaway message
        try:
            guild   = self.bot.get_guild(gw["guild_id"])
            channel = guild.get_channel(gw["channel_id"]) if guild else None
            if channel:
                msg  = await channel.fetch_message(int(key))
                host = guild.get_member(gw["host_id"]) or await self.bot.fetch_user(gw["host_id"])
                ends_at = datetime.fromisoformat(gw["ends_at"])
                mentions = [f"<@{w}>" for w in winners]
                new_emb  = self._build_embed(
                    prize           = gw["prize"],
                    host            = host,
                    ends_at         = ends_at,
                    winner_count    = gw["winners"],
                    entries         = len(entries),
                    ended           = True,
                    winner_mentions = mentions,
                )
                # Disable enter button on end
                disabled_view = discord.ui.View()
                disabled_btn  = discord.ui.Button(
                    label    = "🏁  Giveaway Ended",
                    style    = discord.ButtonStyle.secondary,
                    disabled = True,
                )
                disabled_view.add_item(disabled_btn)
                await msg.edit(embed=new_emb, view=disabled_view)

                # Announce winners
                if winners:
                    winner_str = ", ".join(f"<@{w}>" for w in winners)
                    await channel.send(
                        f"🎉 Congratulations {winner_str}! "
                        f"You won **{gw['prize']}**!\n"
                        f"Please open a ticket to claim your prize."
                    )
                else:
                    await channel.send(
                        f"😔 The **{gw['prize']}** giveaway ended with no valid entries."
                    )
        except Exception:
            pass

        return winners

    # ── Background task ───────────────────────────────────────────────────────

    @tasks.loop(seconds=60)
    async def check_ended(self) -> None:
        now  = datetime.now(timezone.utc)
        data = await self.store.read()
        for key, gw in list(data.get("giveaways", {}).items()):
            if gw.get("ended"):
                continue
            try:
                ends_at = datetime.fromisoformat(gw["ends_at"])
            except Exception:
                continue
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=timezone.utc)
            if now >= ends_at:
                async with self._lock:
                    data = await self.store.read()
                    if not data["giveaways"].get(key, {}).get("ended"):
                        await self._end_giveaway(key, data)

    @check_ended.before_loop
    async def before_check(self) -> None:
        await self.bot.wait_until_ready()

    # ── Duration parser ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_duration(text: str) -> Optional[int]:
        """Returns total seconds or None."""
        import re
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        m = re.fullmatch(r"(\d+)([smhdw])", (text or "").strip().lower())
        if not m:
            return None
        n, unit = int(m.group(1)), m.group(2)
        return n * units[unit] if n > 0 else None

    # ── Commands ──────────────────────────────────────────────────────────────

    group = app_commands.Group(name="giveaway", description="Giveaway commands.")

    @group.command(name="start", description="Start a giveaway. Staff only.")
    @app_commands.describe(
        channel       = "Channel to post the giveaway in",
        prize         = "What's being given away",
        duration      = "How long to run (e.g. 1h, 30m, 2d, 1w)",
        winners       = "Number of winners (default 1)",
        required_role = "Role required to enter (optional)",
    )
    async def giveaway_start(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        prize: str,
        duration: str,
        winners: int = 1,
        required_role: Optional[discord.Role] = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        seconds = self._parse_duration(duration)
        if not seconds:
            return await interaction.response.send_message(
                "Invalid duration. Examples: `30m`, `1h`, `2d`, `1w`.", ephemeral=True
            )
        if winners < 1:
            winners = 1
        if winners > 20:
            return await interaction.response.send_message("Max 20 winners.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        ends_at = datetime.now(timezone.utc).replace(microsecond=0)
        from datetime import timedelta
        ends_at = ends_at + timedelta(seconds=seconds)

        emb = self._build_embed(
            prize         = prize,
            host          = interaction.user,
            ends_at       = ends_at,
            winner_count  = winners,
            entries       = 0,
            required_role = required_role,
        )

        # Post with a placeholder view — we update custom_id after we have the message ID
        placeholder_view = discord.ui.View()
        placeholder_view.add_item(discord.ui.Button(
            label     = "🎉  Enter Giveaway",
            style     = discord.ButtonStyle.success,
            custom_id = "mangomods:giveaway:enter:0",
        ))
        msg = await channel.send(embed=emb, view=placeholder_view)

        # Now register the real persistent view with the correct message ID
        real_view = GiveawayEnterView(self.bot, msg.id)
        self.bot.add_view(real_view)
        await msg.edit(view=real_view)

        # Persist
        data = await self.store.read()
        data.setdefault("giveaways", {})[str(msg.id)] = {
            "message_id":      msg.id,
            "channel_id":      channel.id,
            "guild_id":        interaction.guild.id,
            "prize":           prize,
            "winners":         winners,
            "host_id":         interaction.user.id,
            "ends_at":         ends_at.isoformat(),
            "ended":           False,
            "entries":         [],
            "winner_ids":      [],
            "required_role_id": required_role.id if required_role else None,
        }
        await self.store.write(data)

        await log_action(
            self.bot,
            "Giveaway Started",
            f"By {interaction.user.mention}\n"
            f"Prize: **{prize}** | Winners: **{winners}** | Ends: <t:{int(ends_at.timestamp())}:R>"
            + (f"\nRequired role: {required_role.mention}" if required_role else ""),
        )

        await interaction.followup.send(
            f"✅ Giveaway for **{prize}** started in {channel.mention}.", ephemeral=True
        )

    @group.command(name="end", description="End a giveaway early and pick winners now. Staff only.")
    @app_commands.describe(message_id="Message ID of the giveaway to end")
    async def giveaway_end(
        self,
        interaction: discord.Interaction,
        message_id: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        async with self._lock:
            data = await self.store.read()
            gw   = data.get("giveaways", {}).get(message_id)

            if not gw:
                return await interaction.followup.send("Giveaway not found.", ephemeral=True)
            if gw.get("ended"):
                return await interaction.followup.send("That giveaway already ended.", ephemeral=True)
            if gw["guild_id"] != interaction.guild.id:
                return await interaction.followup.send("That giveaway isn't in this server.", ephemeral=True)

            winners = await self._end_giveaway(message_id, data, early=True)

        winner_str = ", ".join(f"<@{w}>" for w in winners) if winners else "No entries"
        await log_action(
            self.bot,
            "Giveaway Ended Early",
            f"By {interaction.user.mention}\nMessage ID: {message_id}\nWinners: {winner_str}",
        )
        await interaction.followup.send(
            f"✅ Giveaway ended. Winners: {winner_str or 'none (no entries)'}.", ephemeral=True
        )

    @group.command(name="reroll", description="Reroll winners for a finished giveaway. Staff only.")
    @app_commands.describe(message_id="Message ID of the ended giveaway")
    async def giveaway_reroll(
        self,
        interaction: discord.Interaction,
        message_id: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        data = await self.store.read()
        gw   = data.get("giveaways", {}).get(message_id)

        if not gw:
            return await interaction.followup.send("Giveaway not found.", ephemeral=True)
        if not gw.get("ended"):
            return await interaction.followup.send(
                "That giveaway hasn't ended yet. Use `/giveaway end` first.", ephemeral=True
            )
        if gw["guild_id"] != interaction.guild.id:
            return await interaction.followup.send("That giveaway isn't in this server.", ephemeral=True)

        entries = gw.get("entries", [])
        count   = int(gw.get("winners", 1))
        if not entries:
            return await interaction.followup.send("No entries to reroll from.", ephemeral=True)

        new_winners = random.sample(entries, min(count, len(entries)))
        gw["winner_ids"] = new_winners
        await self.store.write(data)

        # Announce in the giveaway channel
        try:
            guild   = interaction.guild
            channel = guild.get_channel(gw["channel_id"])
            if channel:
                winner_str = ", ".join(f"<@{w}>" for w in new_winners)
                await channel.send(
                    f"🔄 **Reroll!** New winner{'s' if len(new_winners) > 1 else ''} for "
                    f"**{gw['prize']}**: {winner_str}! "
                    f"Please open a ticket to claim your prize."
                )
        except Exception:
            pass

        winner_str = ", ".join(f"<@{w}>" for w in new_winners)
        await log_action(
            self.bot,
            "Giveaway Rerolled",
            f"By {interaction.user.mention}\nPrize: **{gw['prize']}**\nNew winners: {winner_str}",
        )
        await interaction.followup.send(
            f"✅ Rerolled. New winners: {winner_str}.", ephemeral=True
        )

    @group.command(name="list", description="List active giveaways in this server.")
    async def giveaway_list(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        data   = await self.store.read()
        active = [
            gw for gw in data.get("giveaways", {}).values()
            if not gw.get("ended") and gw["guild_id"] == interaction.guild.id
        ]

        if not active:
            return await interaction.followup.send(
                "No active giveaways in this server.", ephemeral=True
            )

        emb = mango_embed(self.bot, title="🎁  Active Giveaways", color="premium", footer="Giveaways")

        for gw in active:
            ends_at = datetime.fromisoformat(gw["ends_at"])
            emb.add_field(
                name  = gw["prize"],
                value = (
                    f"Channel: <#{gw['channel_id']}>\n"
                    f"Winners: **{gw['winners']}** | Entries: **{len(gw.get('entries', []))}**\n"
                    f"Ends: <t:{int(ends_at.timestamp())}:R>"
                ),
                inline = False,
            )

        await interaction.followup.send(embed=emb, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaways(bot))
