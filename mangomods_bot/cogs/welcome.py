from __future__ import annotations

import discord
from discord.ext import commands

from mangomods_bot.utils.embeds import mango_embed
from mangomods_bot.utils.log import log_action

# ─────────────────────────────────────────────────────────────────────────────
# Paste your #create-a-ticket channel link here.
# Right-click the channel in Discord → "Copy Link"
# Example: https://discord.com/channels/123456789012345678/987654321098765432
# ─────────────────────────────────────────────────────────────────────────────
TICKET_CHANNEL_URL = "https://discord.com/channels/GUILD_ID/CHANNEL_ID"


class WelcomeView(discord.ui.View):
    """Persistent link-button row attached to every welcome message."""

    def __init__(self, website_url: str) -> None:
        super().__init__(timeout=None)

        self.add_item(
            discord.ui.Button(
                label="🌐  Visit Website",
                style=discord.ButtonStyle.link,
                url=website_url,
            )
        )
        self.add_item(
            discord.ui.Button(
                label="🎫  Create a Ticket",
                style=discord.ButtonStyle.link,
                url=TICKET_CHANNEL_URL,
            )
        )


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._send_welcome(member)
        await log_action(
            self.bot,
            "Member Joined",
            f"{member.mention} (`{member.id}`) joined the server.",
        )

    async def _send_welcome(self, member: discord.Member) -> None:
        try:
            ch = self.bot.get_channel(
                self.bot.config.welcome_channel_id
            ) or await self.bot.fetch_channel(self.bot.config.welcome_channel_id)

            if not isinstance(ch, discord.TextChannel):
                return

            website = self.bot.config.website_url
            guild   = member.guild

            emb = mango_embed(self.bot)
            emb.title = f"🥭  Welcome to {guild.name}!"
            emb.description = (
                f"Hey {member.mention}, glad you're here!\n\n"
                "**MangoMods** provides top-tier cheats backed by the best support "
                "in the industry. Here's how to get started:\n\n"
                "📜  **Read the Rules** — head to the rules channel and acknowledge "
                "them to unlock full access.\n"
                "🎫  **Need Help?** — open a support ticket using the button below.\n"
                f"🌐  **Browse Products** — check out everything we offer at **{website}**."
            )

            emb.add_field(
                name="📌  Quick Info",
                value=(
                    f"› **Server:** {guild.name}\n"
                    f"› **Members:** {guild.member_count:,}\n"
                    f"› **Website:** [{website}]({website})"
                ),
                inline=False,
            )

            if member.display_avatar:
                emb.set_thumbnail(url=member.display_avatar.url)

            if guild.icon:
                emb.set_author(name=guild.name, icon_url=guild.icon.url)

            emb.set_footer(text="MangoMods  •  Welcome")

            view = WelcomeView(website)
            await ch.send(content=member.mention, embed=emb, view=view)

        except Exception:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))