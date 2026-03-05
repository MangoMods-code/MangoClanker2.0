from __future__ import annotations

import asyncio
import discord
from discord.ext import commands
from discord import app_commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import mango_embed


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────

class Sticky(commands.Cog):
    """
    Sticky messages — keeps a message pinned to the bottom of a channel.
    Every time someone sends a message, the old sticky is deleted and reposted.

    Commands:
      /sticky set     — stick a message in the current channel
      /sticky clear   — remove the sticky from the current channel
      /sticky show    — display the current sticky content (ephemeral)
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store = JSONStore(
            "/data/sticky.json",
            {},  # { "channel_id": { "content": str, "message_id": int | None } }
        )
        # Per-channel cooldown to avoid repost spam when messages come in fast
        self._cooldowns: dict[int, asyncio.Task] = {}

    # ── helpers ───────────────────────────────────────────────────────────────

    def _is_staff(self, member: discord.Member) -> bool:
        staff_id = getattr(self.bot.config, "staff_role_id", None)
        owner_id = getattr(self.bot.config, "owner_role_id", None)
        return any(r.id in {staff_id, owner_id} for r in member.roles)

    async def _delete_old_sticky(
        self, channel: discord.TextChannel, message_id: int | None
    ) -> None:
        if not message_id:
            return
        try:
            msg = await channel.fetch_message(message_id)
            await msg.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    async def _post_sticky(
        self, channel: discord.TextChannel, content: str
    ) -> discord.Message:
        embed = mango_embed(self.bot)
        embed.description = content
        embed.set_footer(text="📌  Sticky message")
        return await channel.send(embed=embed)

    async def _repost(self, channel: discord.TextChannel) -> None:
        """Delete the old sticky and repost it at the bottom."""
        data = await self.store.read()
        entry = data.get(str(channel.id))
        if not entry:
            return

        await _delete_old_sticky_static(channel, entry.get("message_id"))

        new_msg = await self._post_sticky(channel, entry["content"])

        entry["message_id"] = new_msg.id
        data[str(channel.id)] = entry
        await self.store.write(data)

    # ── event: repost sticky on new message ──────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Ignore DMs, bots (including ourselves), and system messages
        if not isinstance(message.channel, discord.TextChannel):
            return
        if message.author.bot:
            return

        data = await self.store.read()
        entry = data.get(str(message.channel.id))
        if not entry:
            return

        channel = message.channel
        cid = channel.id

        # Cancel any pending repost for this channel (debounce)
        existing = self._cooldowns.get(cid)
        if existing and not existing.done():
            existing.cancel()

        async def delayed_repost():
            await asyncio.sleep(1.0)  # short delay so burst messages only trigger one repost
            await self._repost(channel)

        task = asyncio.create_task(delayed_repost())
        self._cooldowns[cid] = task

    # ── command group ─────────────────────────────────────────────────────────

    sticky_group = app_commands.Group(name="sticky", description="Sticky message management.")

    @sticky_group.command(name="set", description="Stick a message to the bottom of this channel.")
    @app_commands.describe(message="The message to stick.")
    async def sticky_set(self, interaction: discord.Interaction, message: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message(
                "This only works in text channels.", ephemeral=True
            )

        channel = interaction.channel
        data = await self.store.read()
        existing = data.get(str(channel.id))

        # Delete old sticky if one exists
        if existing:
            await _delete_old_sticky_static(channel, existing.get("message_id"))

        # Acknowledge the slash command first so Discord doesn't time out
        await interaction.response.send_message(
            f"📌 Sticky set in {channel.mention}.", ephemeral=True
        )

        # Post the sticky
        sticky_msg = await self._post_sticky(channel, message)

        data[str(channel.id)] = {
            "content": message,
            "message_id": sticky_msg.id,
        }
        await self.store.write(data)

    @sticky_group.command(name="clear", description="Remove the sticky from this channel.")
    async def sticky_clear(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message(
                "This only works in text channels.", ephemeral=True
            )

        channel = interaction.channel
        data = await self.store.read()
        entry = data.pop(str(channel.id), None)

        if not entry:
            return await interaction.response.send_message(
                "There's no sticky set in this channel.", ephemeral=True
            )

        await _delete_old_sticky_static(channel, entry.get("message_id"))
        await self.store.write(data)

        # Cancel any pending repost
        task = self._cooldowns.pop(channel.id, None)
        if task and not task.done():
            task.cancel()

        await interaction.response.send_message(
            f"🗑️ Sticky removed from {channel.mention}.", ephemeral=True
        )

    @sticky_group.command(name="show", description="Show the current sticky content in this channel.")
    async def sticky_show(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message(
                "This only works in text channels.", ephemeral=True
            )

        data = await self.store.read()
        entry = data.get(str(interaction.channel.id))

        if not entry:
            return await interaction.response.send_message(
                "There's no sticky set in this channel.", ephemeral=True
            )

        await interaction.response.send_message(
            f"📌 **Current sticky:**\n{entry['content']}", ephemeral=True
        )


# ── module-level helper (avoids passing self to _delete) ─────────────────────

async def _delete_old_sticky_static(
    channel: discord.TextChannel, message_id: int | None
) -> None:
    if not message_id:
        return
    try:
        msg = await channel.fetch_message(message_id)
        await msg.delete()
    except (discord.NotFound, discord.Forbidden):
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))