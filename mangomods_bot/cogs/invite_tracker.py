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


class InviteTracker(commands.Cog):
    """
    Tracks which invite link brought each new member.

    How it works:
      - On ready: snapshot all current invite use-counts into memory.
      - On member join: diff the snapshot against the current invite list.
        The invite whose use-count increased is the one they used.
      - Stores per-member attribution in /data/invites.json.
      - Stores per-inviter total counts in the same file.

    Commands:
      /invites [@member]   — see how many members someone has invited
      /inviteof @member    — see which invite code brought this member in
      /invitetop           — leaderboard of top inviters
      /invitereset @member — staff: reset a member's invite count
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot   = bot
        self.store = JSONStore("/data/invites.json", {
            "attributed": {},   # { user_id: { "inviter_id": int, "code": str, "joined_at": str } }
            "counts":     {},   # { inviter_id: int }
        })
        # In-memory snapshot: { guild_id: { code: uses } }
        self._snapshot: dict[int, dict[str, int]] = {}

    # ── Snapshot helpers ──────────────────────────────────────────────────────

    async def _take_snapshot(self, guild: discord.Guild) -> None:
        try:
            invites = await guild.invites()
            self._snapshot[guild.id] = {inv.code: inv.uses or 0 for inv in invites}
        except discord.Forbidden:
            pass
        except Exception:
            pass

    async def _find_used_invite(
        self, guild: discord.Guild
    ) -> Optional[discord.Invite]:
        """
        Diff current invite uses against the snapshot.
        Returns the invite whose use-count went up by 1, or None.
        """
        try:
            current = await guild.invites()
        except discord.Forbidden:
            return None
        except Exception:
            return None

        old_snap = self._snapshot.get(guild.id, {})
        found    = None

        for inv in current:
            old_uses = old_snap.get(inv.code, 0)
            new_uses = inv.uses or 0
            if new_uses > old_uses:
                found = inv
                break

        # Update snapshot regardless
        self._snapshot[guild.id] = {inv.code: inv.uses or 0 for inv in current}
        return found

    # ── Listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self._take_snapshot(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild:
            snap = self._snapshot.setdefault(invite.guild.id, {})
            snap[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild:
            self._snapshot.get(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return

        invite = await self._find_used_invite(member.guild)

        data = await self.store.read()
        uid  = str(member.id)

        if invite and invite.inviter:
            inviter_id  = str(invite.inviter.id)
            inviter_name = str(invite.inviter)

            # Record attribution
            data.setdefault("attributed", {})[uid] = {
                "inviter_id":   int(inviter_id),
                "inviter_name": inviter_name,
                "code":         invite.code,
                "joined_at":    datetime.now(timezone.utc).isoformat(),
            }

            # Increment inviter count
            data.setdefault("counts", {})
            data["counts"][inviter_id] = data["counts"].get(inviter_id, 0) + 1

            await self.store.write(data)

            await log_action(
                self.bot,
                "Invite Tracked",
                f"User: {member.mention} (`{member.id}`)\n"
                f"Invited by: {invite.inviter.mention} (`{invite.inviter.id}`)\n"
                f"Code: `{invite.code}` | Total invites for inviter: **{data['counts'][inviter_id]}**",
            )
        else:
            # Could be a vanity URL, unknown, or bot couldn't read invites
            data.setdefault("attributed", {})[uid] = {
                "inviter_id":   None,
                "inviter_name": None,
                "code":         "unknown",
                "joined_at":    datetime.now(timezone.utc).isoformat(),
            }
            await self.store.write(data)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """
        When someone leaves, decrement the inviter's count.
        We don't delete the attribution record — just adjust the live count.
        """
        if member.bot:
            return

        data = await self.store.read()
        attr = data.get("attributed", {}).get(str(member.id), {})
        inviter_id = attr.get("inviter_id")

        if inviter_id:
            counts = data.setdefault("counts", {})
            key    = str(inviter_id)
            counts[key] = max(0, counts.get(key, 1) - 1)
            await self.store.write(data)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_staff(self, member: discord.Member) -> bool:
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

    # ── Commands ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="invites",
        description="See how many members someone has invited.",
    )
    @app_commands.describe(member="Member to check (defaults to yourself)")
    async def invites(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")

        target = member or interaction.user

        # Non-staff can only look up themselves
        if target.id != interaction.user.id and not self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only for looking up others.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        data  = await self.store.read()
        count = data.get("counts", {}).get(str(target.id), 0)

        emb = mango_embed(self.bot, color="info", footer="Invite Tracker")
        emb.title = f"📨  Invites — {target.display_name}"
        emb.set_thumbnail(url=target.display_avatar.url)
        emb.add_field(name="Total Invites", value=str(count), inline=True)
        emb.add_field(name="Member",        value=target.mention, inline=True)

        await interaction.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(
        name="inviteof",
        description="See which invite link brought a member in. Staff only.",
    )
    @app_commands.describe(member="Member to check")
    async def inviteof(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        data = await self.store.read()
        attr = data.get("attributed", {}).get(str(member.id))

        if not attr:
            return await interaction.followup.send(
                f"No invite attribution on record for {member.mention}. "
                "They may have joined before the tracker was active.",
                ephemeral=True,
            )

        inviter_id   = attr.get("inviter_id")
        inviter_name = attr.get("inviter_name", "Unknown")
        code         = attr.get("code", "unknown")
        joined_at    = attr.get("joined_at")

        emb = mango_embed(self.bot, color="info", footer="Invite Tracker")
        emb.title = f"📨  Invite Attribution — {member.display_name}"
        emb.set_thumbnail(url=member.display_avatar.url)

        emb.add_field(
            name  = "Invited By",
            value = f"<@{inviter_id}> (`{inviter_name}`)" if inviter_id else "Unknown",
            inline=True,
        )
        emb.add_field(name="Code", value=f"`{code}`", inline=True)

        if joined_at:
            try:
                ts = datetime.fromisoformat(joined_at)
                emb.add_field(
                    name  = "Joined",
                    value = f"<t:{int(ts.timestamp())}:F> (<t:{int(ts.timestamp())}:R>)",
                    inline=False,
                )
            except Exception:
                pass

        await interaction.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(
        name="invitetop",
        description="Leaderboard of top inviters in this server. Staff only.",
    )
    async def invitetop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        data   = await self.store.read()
        counts = data.get("counts", {})

        if not counts:
            return await interaction.followup.send(
                "No invite data yet.", ephemeral=True
            )

        # Sort descending, top 15
        sorted_counts = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:15]

        emb = mango_embed(
            self.bot,
            title = "📊  Top Inviters",
            color = "info",
            footer= "Invite Tracker",
        )

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, count) in enumerate(sorted_counts):
            prefix = medals[i] if i < 3 else f"**#{i+1}**"
            lines.append(f"{prefix}  <@{uid}> — **{count}** invite{'s' if count != 1 else ''}")

        emb.description = "\n".join(lines)
        await interaction.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(
        name="invitereset",
        description="Reset a member's invite count. Staff only.",
    )
    @app_commands.describe(member="Member to reset")
    async def invitereset(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this in a server.")
        if not self._is_staff(interaction.user):
            return await self._ephemeral(interaction, "Staff only.")

        await interaction.response.defer(ephemeral=True, thinking=True)

        data = await self.store.read()
        key  = str(member.id)
        old  = data.get("counts", {}).get(key, 0)
        data.setdefault("counts", {})[key] = 0
        await self.store.write(data)

        await log_action(
            self.bot,
            "Invite Count Reset",
            f"Staff: {interaction.user.mention}\n"
            f"User: {member.mention} (`{member.id}`)\n"
            f"Previous count: **{old}** → **0**",
        )

        await interaction.followup.send(
            f"✅ Reset invite count for {member.mention} (was **{old}**).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InviteTracker(bot))
