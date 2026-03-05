from __future__ import annotations

import os
import random
import time
import discord
from discord.ext import commands
from discord import app_commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.log import log_action
from mangomods_bot.utils.embeds import mango_embed


def _int_env(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)) or str(default))
    except Exception:
        return default


CODE_TTL = 600  # seconds — code expires after 10 minutes


# ──────────────────────────────────────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────────────────────────────────────

class VerifyModal(discord.ui.Modal, title="MangoMods Verification"):
    answer = discord.ui.TextInput(
        label="Enter the 4-digit code sent to your DMs",
        placeholder="Example: 4921",
        max_length=8,
        required=True,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        cog = self.bot.get_cog("Verification")
        if not cog:
            return await interaction.response.send_message(
                "Verification system not loaded.", ephemeral=True
            )
        await cog.handle_verify_submit(interaction, str(self.answer).strip())


class RulesView(discord.ui.View):
    """Step 1 — Posted in the rules channel."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="✅  I've Read & Agree to the Rules",
        style=discord.ButtonStyle.success,
        custom_id="mangomods:rules:ack",
    )
    async def ack(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self.bot.get_cog("Verification")
        if not cog:
            return await interaction.response.send_message(
                "Verification system not loaded.", ephemeral=True
            )
        await cog.acknowledge_rules(interaction)


class VerifyView(discord.ui.View):
    """Step 2 — Posted in the verify channel.
    
    First click  → sends DM code, stores it, tells user to check DMs then click again.
    Second click → opens the modal to enter the code.
    """

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="🔒  Verify",
        style=discord.ButtonStyle.primary,
        custom_id="mangomods:rules:verify",
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self.bot.get_cog("Verification")
        if not cog:
            return await interaction.response.send_message(
                "Verification system not loaded.", ephemeral=True
            )
        await cog.start_verify(interaction)


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────

class Verification(commands.Cog):
    """
    Mandatory two-step gate:
      1) Rules channel  -> click "I've Read & Agree" -> records ack, directs to verify channel.
      2) Verify channel -> first click sends DM code and stores it.
                       -> second click opens modal to enter the code -> gets member role.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store = JSONStore(
            "/data/verification.json",
            {"acknowledged": {}, "verified": {}, "pending_codes": {}},
        )
        self.rules_channel_id  = _int_env("RULES_CHANNEL_ID")
        self.verify_channel_id = _int_env("VERIFICATION_CHANNEL_ID")
        self.member_role_id    = _int_env("MEMBER_ROLE_ID")

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _ephemeral(self, interaction: discord.Interaction, msg: str):
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async def _grant_member_role(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False

        if not self.member_role_id:
            await self._ephemeral(interaction, "⚠️ MEMBER_ROLE_ID is not configured.")
            return False

        role = interaction.guild.get_role(self.member_role_id)
        if not role:
            await self._ephemeral(
                interaction, "⚠️ Member role not found — check MEMBER_ROLE_ID in .env."
            )
            return False

        if role in interaction.user.roles:
            await self._ephemeral(interaction, "✅ You're already verified and have access.")
            return False

        try:
            await interaction.user.add_roles(
                role, reason="Completed verification (rules ack + DM code)"
            )
        except discord.Forbidden:
            await self._ephemeral(interaction, "❌ I don't have permission to assign roles.")
            return False
        except Exception:
            await self._ephemeral(interaction, "❌ Unexpected error while assigning role.")
            return False

        await log_action(
            self.bot,
            "Member Role Granted",
            f"User: {interaction.user.mention} (`{interaction.user.id}`)\n"
            f"Role: {role.mention} — completed two-step verification",
        )
        return True

    # ── step 1: acknowledge rules ─────────────────────────────────────────────

    async def acknowledge_rules(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this inside the server.")

        data = await self.store.read()

        if data.get("verified", {}).get(str(interaction.user.id)):
            return await self._ephemeral(
                interaction, "✅ You're already verified and have server access."
            )

        if data.get("acknowledged", {}).get(str(interaction.user.id)):
            verify_ch = interaction.guild.get_channel(self.verify_channel_id)
            mention = verify_ch.mention if verify_ch else "the verify channel"
            return await self._ephemeral(
                interaction,
                f"✅ You've already agreed to the rules. Head to {mention} to complete verification.",
            )

        data.setdefault("acknowledged", {})
        data["acknowledged"][str(interaction.user.id)] = True
        await self.store.write(data)

        await log_action(
            self.bot,
            "Rules Acknowledged",
            f"User: {interaction.user.mention} (`{interaction.user.id}`)",
        )

        verify_ch = interaction.guild.get_channel(self.verify_channel_id)
        mention = verify_ch.mention if verify_ch else "the verify channel"
        await self._ephemeral(
            interaction,
            f"✅ Rules acknowledged!\n\n"
            f"Now head to {mention} and click **Verify** to receive your code in DMs. 🥭",
        )

    # ── step 2: two-click DM code verification ────────────────────────────────

    async def start_verify(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this inside the server.")

        data = await self.store.read()
        uid = str(interaction.user.id)

        # Already fully verified
        if data.get("verified", {}).get(uid):
            return await self._ephemeral(
                interaction, "✅ You're already verified and have server access."
            )

        # Must ack rules first
        if not data.get("acknowledged", {}).get(uid):
            rules_ch = interaction.guild.get_channel(self.rules_channel_id)
            mention = rules_ch.mention if rules_ch else "the rules channel"
            return await self._ephemeral(
                interaction,
                f"❌ You need to agree to the rules first.\n\n"
                f"Head to {mention}, click **I've Read & Agree to the Rules**, then come back here.",
            )

        pending = data.get("pending_codes", {}).get(uid)
        now = time.time()

        # ── Second click: valid code already waiting → open modal ────────────
        if pending and (now - pending["issued_at"]) < CODE_TTL:
            return await interaction.response.send_modal(VerifyModal(self.bot))

        # ── First click (or expired code): generate and DM new code ──────────
        code = str(random.randint(1000, 9999))

        try:
            await interaction.user.send(
                f"🔒 **MangoMods Verification Code**\n\n"
                f"Your code is: **{code}**\n\n"
                f"Go back to the server and click **Verify** again to enter it.\n"
                f"This code expires in 10 minutes. Do not share it with anyone."
            )
        except discord.Forbidden:
            return await self._ephemeral(
                interaction,
                "❌ I couldn't send you a DM.\n\n"
                "Please enable **Allow direct messages from server members** in your "
                "Privacy Settings, then click **Verify** again.",
            )
        except Exception:
            return await self._ephemeral(
                interaction,
                "❌ Failed to send your verification code. Please try again in a moment.",
            )

        # Store the code
        data.setdefault("pending_codes", {})
        data["pending_codes"][uid] = {"code": code, "issued_at": now}
        await self.store.write(data)

        await self._ephemeral(
            interaction,
            "📨 **Code sent to your DMs!**\n\n"
            "Check your DMs for the 4-digit code, then come back here and click "
            "**Verify** again to enter it.\n\n"
            "*The code expires in 10 minutes.*",
        )

    async def handle_verify_submit(self, interaction: discord.Interaction, user_answer: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use this inside the server.", ephemeral=True
            )

        data = await self.store.read()
        uid = str(interaction.user.id)

        pending = data.get("pending_codes", {}).get(uid)
        now = time.time()

        if not pending:
            return await interaction.response.send_message(
                "❌ No pending code found. Click **Verify** to get a new code.", ephemeral=True
            )

        if (now - pending["issued_at"]) >= CODE_TTL:
            # Clear expired code
            data["pending_codes"].pop(uid, None)
            await self.store.write(data)
            return await interaction.response.send_message(
                "❌ Your code has expired. Click **Verify** again to get a new one.", ephemeral=True
            )

        if user_answer != pending["code"]:
            return await interaction.response.send_message(
                "❌ Incorrect code. Click **Verify** again to receive a new code.", ephemeral=True
            )

        # Code correct — clean up and grant role
        data.setdefault("verified", {})
        data["verified"][uid] = True
        data.get("pending_codes", {}).pop(uid, None)
        await self.store.write(data)

        await log_action(
            self.bot,
            "User Verified",
            f"User: {interaction.user.mention} (`{interaction.user.id}`)\n"
            f"Passed DM code check — granting member role.",
        )

        granted = await self._grant_member_role(interaction)
        if granted:
            role = interaction.guild.get_role(self.member_role_id)
            role_mention = role.mention if role else "the member role"
            await self._ephemeral(
                interaction,
                f"✅ Verification complete! You've been given {role_mention} — welcome to MangoMods! 🥭",
            )

    # ── slash command ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="setupverify",
        description="Post the Rules and Verification panels (staff only).",
    )
    async def setupverify(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use this in a server.", ephemeral=True
            )

        if not any(
            r.id == self.bot.config.staff_role_id for r in interaction.user.roles
        ):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        if not self.rules_channel_id or not self.verify_channel_id:
            return await interaction.response.send_message(
                "Set `RULES_CHANNEL_ID` and `VERIFICATION_CHANNEL_ID` in .env",
                ephemeral=True,
            )

        rules_ch = interaction.guild.get_channel(self.rules_channel_id)
        ver_ch   = interaction.guild.get_channel(self.verify_channel_id)

        if not isinstance(rules_ch, discord.TextChannel) or not isinstance(
            ver_ch, discord.TextChannel
        ):
            return await interaction.response.send_message(
                "Invalid channel IDs in .env.", ephemeral=True
            )

        # ── Rules embed ───────────────────────────────────────────────────────
        rules_embed = mango_embed(self.bot)
        rules_embed.title = "📜  MangoMods — Server Rules"
        rules_embed.description = (
            "Welcome to MangoMods. To keep this community enjoyable for everyone, "
            "all members are expected to follow the rules below. "
            "Failure to do so may result in a timeout, kick, or permanent ban.\n\n"
            "`01` 🤝  **Respect Everyone**\n"
            "Treat all members and staff with basic respect. No harassment, bullying, "
            "hate speech, or targeted drama. Disagree maturely or take it to a ticket.\n\n"
            "`02` 💬  **Keep Feedback Constructive**\n"
            "Criticism and suggestions are always welcome, but keep it civil. "
            "Talking down to staff or other members won't be tolerated.\n\n"
            "`03` 🎫  **No Support Spam**\n"
            "One ticket at a time. Don't spam DMs to staff or members. "
            "Abuse of the ticket system will result in a timeout.\n\n"
            "`04` 😎  **Keep the Vibe Right**\n"
            "No unnecessary toxicity, excessive negativity, or attempts to stir drama. "
            "This is a chill community — keep it that way.\n\n"
            "`05` 🔞  **No NSFW or Disturbing Content**\n"
            "Zero tolerance for nudity, sexual content, extreme gore, graphic violence, "
            "or anything disturbing — including links, images, and videos.\n\n"
            "`06` 📣  **No Unsolicited Self-Promotion**\n"
            "No advertising, server invites, or referral links unless you have explicit "
            "staff approval. This applies to DMs as well.\n\n"
            "`07` ⚖️  **Follow Discord's Terms of Service**\n"
            "All members must comply with Discord's ToS. No ban evasion, alt accounts "
            "to bypass punishments, or behaviour that puts this server at risk.\n\n"
            "`08` 🔑  **No Account Sharing or Selling**\n"
            "Do not share, sell, or transfer your MangoMods account or products. "
            "Accounts found doing so will be terminated without a refund.\n\n"
            "`09` 💳  **No Chargebacks or Fraud**\n"
            "Issuing a chargeback = immediate permanent ban. If you have a billing "
            "issue, open a ticket — we will sort it out properly.\n\n"
            "`10` 🛡️  **Staff Decisions Are Final**\n"
            "Disagree with a mod action? Open a ticket calmly and explain your case. "
            "Arguing publicly or disrespecting staff will not help your situation.\n\n"
            "`11` 🏅  **Want to Join the Team?**\n"
            "Ask a staff member about an application to start as a Trial Mod. "
            "Do not DM staff unsolicited asking for roles.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Step 1 of 2 — Agree below, then head to {ver_ch.mention} to complete verification.*"
        )
        rules_embed.set_footer(text="MangoMods  •  Step 1 of 2 — Rules")

        # ── Verify embed ──────────────────────────────────────────────────────
        verify_embed = mango_embed(self.bot)
        verify_embed.title = "🔒  MangoMods — Verification"
        verify_embed.description = (
            f"**Step 2 of 2** — Complete this step to unlock the server.\n\n"
            f"If you haven't already, head to {rules_ch.mention} first and agree to the rules.\n\n"
            "**How it works:**\n"
            "**1.** Click **Verify** — the bot will send a 4-digit code to your DMs.\n"
            "**2.** Check your DMs for the code.\n"
            "**3.** Click **Verify** again and enter the code in the pop-up.\n\n"
            "⚠️ Make sure **Allow direct messages from server members** is enabled in your "
            "Privacy Settings before clicking, otherwise the code can't be delivered."
        )
        verify_embed.set_footer(text="MangoMods  •  Step 2 of 2 — Verification")

        await rules_ch.send(embed=rules_embed, view=RulesView(self.bot))
        await ver_ch.send(embed=verify_embed, view=VerifyView(self.bot))

        await interaction.response.send_message(
            "✅ Rules + Verification panels posted.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))