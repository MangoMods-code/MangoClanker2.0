from __future__ import annotations

import os
import random
import time
from datetime import datetime, timezone, timedelta

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


CODE_TTL        = 600   # code expires after 10 minutes
CODE_RESEND_CD  = 60    # minimum seconds between code requests
MIN_ACCOUNT_AGE = _int_env("MIN_ACCOUNT_AGE_DAYS", 0)  # 0 = disabled


# ──────────────────────────────────────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────────────────────────────────────

class VerifyModal(discord.ui.Modal, title="Enter Your Verification Code"):
    answer = discord.ui.TextInput(
        label="4-digit code from your DMs",
        placeholder="e.g. 4921",
        min_length=4,
        max_length=4,
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
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="✅  I Agree to the Rules",
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
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="🔒  Verify Me",
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
# Embed builders  (kept out of the cog so setupverify stays readable)
# ──────────────────────────────────────────────────────────────────────────────

def _build_rules_embed(bot, verify_ch_mention: str) -> discord.Embed:
    emb = mango_embed(bot)
    emb.title = "📜  MangoMods — Server Rules"
    emb.description = (
        "Welcome to **MangoMods**. Please read every rule before agreeing.\n"
        "Violations may result in a warning, timeout, kick, or permanent ban.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    rules = [
        ("🤝  Respect Everyone",
         "No harassment, bullying, hate speech, or targeted drama. Disagree maturely or open a ticket."),
        ("💬  Constructive Feedback Only",
         "Criticism is welcome — disrespecting staff or members is not."),
        ("🎫  No Support Spam",
         "One ticket at a time. Don't DM staff directly. Abuse of the ticket system = timeout."),
        ("😎  Keep the Vibe Right",
         "No excessive toxicity, negativity, or drama-starting. This is a chill community."),
        ("🔞  No NSFW or Disturbing Content",
         "Zero tolerance — includes links, images, and videos."),
        ("📣  No Unsolicited Promotion",
         "No advertising, server invites, or referral links without explicit staff approval."),
        ("⚖️  Follow Discord ToS",
         "No ban evasion, alt accounts to bypass punishments, or behaviour that risks the server."),
        ("🔑  No Account Sharing or Selling",
         "Sharing or selling your MangoMods account = immediate termination, no refund."),
        ("💳  No Chargebacks or Fraud",
         "Chargebacks = permanent ban. Billing issues belong in a ticket — we will sort it."),
        ("🛡️  Staff Decisions Are Final",
         "Disagree with a mod action? Open a ticket calmly. Arguing publicly makes it worse."),
    ]

    for name, value in rules:
        emb.add_field(name=name, value=value, inline=False)

    emb.add_field(
        name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        value=f"**Step 1 of 2** — Click below to agree, then head to {verify_ch_mention}.",
        inline=False,
    )
    emb.set_footer(text="MangoMods  •  Step 1 of 2 — Rules")
    return emb


def _build_verify_embed(bot, rules_ch_mention: str) -> discord.Embed:
    emb = mango_embed(bot)
    emb.title = "🔒  MangoMods — Verification"
    emb.description = "**Step 2 of 2** — Complete this to unlock the server."

    emb.add_field(
        name="Before you start",
        value=(
            f"Make sure you've agreed to the rules in {rules_ch_mention} first.\n"
            "Enable **Allow direct messages from server members** in your Discord Privacy Settings "
            "— the bot will DM you a code."
        ),
        inline=False,
    )
    emb.add_field(
        name="How it works",
        value=(
            "**1.** Click **Verify Me** below.\n"
            "**2.** Check your DMs for your 4-digit code.\n"
            "**3.** Click **Verify Me** again and enter the code in the pop-up.\n"
            "**4.** Done — you'll get full server access instantly."
        ),
        inline=False,
    )
    emb.add_field(
        name="Code not arriving?",
        value=(
            "Open Discord Settings → Privacy & Safety → "
            "enable **Allow direct messages from server members**, then click Verify Me again."
        ),
        inline=False,
    )
    emb.set_footer(text="MangoMods  •  Step 2 of 2 — Verification")
    return emb


def _build_code_dm_embed(bot, code: str, guild_name: str) -> discord.Embed:
    emb = discord.Embed(
        title="🔒  MangoMods Verification Code",
        colour=discord.Colour(0xF9A826),
        timestamp=datetime.now(timezone.utc),
    )
    emb.add_field(name="Your Code", value=f"```{code}```", inline=False)
    emb.add_field(
        name="Next step",
        value="Go back to the server and click **Verify Me** again to enter this code.",
        inline=False,
    )
    emb.add_field(name="Server",  value=guild_name, inline=True)
    emb.add_field(name="Expires", value="10 minutes", inline=True)
    emb.set_footer(text="Do not share this code with anyone — MangoMods staff will never ask for it.")
    return emb


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────

class Verification(commands.Cog):
    """
    Two-step verification gate with account age gating and staff reset.

    Flow:
      1) #rules      → click "I Agree"  → age check → records ack → directs to #verify
      2) #verify     → first click      → sends DM code (rate-limited to 1 per 60s)
                     → second click     → opens modal → code check → grants member role

    Staff commands:
      /setupverify            — post/refresh both panels
      /resetverification      — wipe a user's state and optionally remove their member role
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

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _ephemeral(self, interaction: discord.Interaction, msg: str, embed: discord.Embed | None = None):
        kwargs = {"ephemeral": True}
        if embed:
            kwargs["embed"] = embed
        else:
            kwargs["content"] = msg
        try:
            if interaction.response.is_done():
                await interaction.followup.send(**kwargs)
            else:
                await interaction.response.send_message(**kwargs)
        except Exception:
            pass

    def _account_age_days(self, member: discord.Member) -> int:
        return (datetime.now(timezone.utc) - member.created_at).days

    async def _flag_new_account(self, guild: discord.Guild, member: discord.Member, age_days: int) -> None:
        await log_action(
            self.bot,
            "⚠️  New Account Flagged — Verification Blocked",
            f"User: {member.mention} (`{member.id}`)\n"
            f"Account age: **{age_days} day(s)** (minimum: {MIN_ACCOUNT_AGE})\n"
            f"Action: blocked at rules step — staff review required.\n"
            f"Use `/resetverification` after reviewing if the account is legitimate.",
        )

    async def _grant_member_role(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False

        if not self.member_role_id:
            await self._ephemeral(interaction, "⚠️ MEMBER_ROLE_ID is not configured.")
            return False

        role = interaction.guild.get_role(self.member_role_id)
        if not role:
            await self._ephemeral(interaction, "⚠️ Member role not found — check MEMBER_ROLE_ID in .env.")
            return False

        if role in interaction.user.roles:
            await self._ephemeral(interaction, "✅ You're already verified.")
            return False

        try:
            await interaction.user.add_roles(role, reason="Completed MangoMods verification")
        except discord.Forbidden:
            await self._ephemeral(interaction, "❌ I don't have permission to assign roles.")
            return False
        except Exception:
            await self._ephemeral(interaction, "❌ Unexpected error assigning role.")
            return False

        await log_action(
            self.bot,
            "Member Verified",
            f"User: {interaction.user.mention} (`{interaction.user.id}`)\n"
            f"Role: {role.mention} granted via DM code verification.",
        )
        return True

    # ── Step 1: Rules acknowledgement ─────────────────────────────────────────

    async def acknowledge_rules(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this inside the server.")

        data = await self.store.read()
        uid  = str(interaction.user.id)

        # Already fully verified
        if data.get("verified", {}).get(uid):
            return await self._ephemeral(interaction, "✅ You're already verified and have full server access.")

        # Already acked
        if data.get("acknowledged", {}).get(uid):
            verify_ch = interaction.guild.get_channel(self.verify_channel_id)
            mention   = verify_ch.mention if verify_ch else "the verify channel"
            return await self._ephemeral(
                interaction,
                f"✅ You've already agreed to the rules.\nHead to {mention} to complete verification.",
            )

        # ── Account age gate ──────────────────────────────────────────────────
        if MIN_ACCOUNT_AGE > 0:
            age_days = self._account_age_days(interaction.user)
            if age_days < MIN_ACCOUNT_AGE:
                await self._flag_new_account(interaction.guild, interaction.user, age_days)

                emb = discord.Embed(
                    title="⚠️  Account Too New",
                    colour=discord.Colour(0xED4245),
                    timestamp=datetime.now(timezone.utc),
                )
                emb.add_field(
                    name="Your account age",
                    value=f"**{age_days} day(s)** old",
                    inline=True,
                )
                emb.add_field(
                    name="Minimum required",
                    value=f"**{MIN_ACCOUNT_AGE} day(s)**",
                    inline=True,
                )
                emb.add_field(
                    name="What happens next",
                    value=(
                        "Your account has been flagged for staff review.\n"
                        "A staff member will verify you manually if your account is legitimate.\n"
                        "Please open a ticket if you believe this is a mistake."
                    ),
                    inline=False,
                )
                emb.set_footer(text="MangoMods  •  Account Age Gate")
                return await self._ephemeral(interaction, "", embed=emb)

        # Record ack
        data.setdefault("acknowledged", {})
        data["acknowledged"][uid] = True
        await self.store.write(data)

        await log_action(
            self.bot,
            "Rules Acknowledged",
            f"User: {interaction.user.mention} (`{interaction.user.id}`)",
        )

        verify_ch = interaction.guild.get_channel(self.verify_channel_id)
        mention   = verify_ch.mention if verify_ch else "the verify channel"

        emb = discord.Embed(
            title="✅  Rules Agreed",
            colour=discord.Colour(0x57F287),
            timestamp=datetime.now(timezone.utc),
        )
        emb.add_field(
            name="Next step",
            value=f"Head to {mention} and click **Verify Me** to complete verification.",
            inline=False,
        )
        emb.set_footer(text="MangoMods  •  Step 1 complete")
        await self._ephemeral(interaction, "", embed=emb)

    # ── Step 2: DM code flow ──────────────────────────────────────────────────

    async def start_verify(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Use this inside the server.")

        data = await self.store.read()
        uid  = str(interaction.user.id)

        # Already verified
        if data.get("verified", {}).get(uid):
            return await self._ephemeral(interaction, "✅ You're already verified and have full server access.")

        # Must ack rules first
        if not data.get("acknowledged", {}).get(uid):
            rules_ch = interaction.guild.get_channel(self.rules_channel_id)
            mention  = rules_ch.mention if rules_ch else "the rules channel"
            emb = discord.Embed(
                title="❌  Rules Not Agreed",
                colour=discord.Colour(0xED4245),
            )
            emb.add_field(
                name="Action required",
                value=f"Head to {mention} and click **I Agree to the Rules** first, then come back here.",
                inline=False,
            )
            return await self._ephemeral(interaction, "", embed=emb)

        pending = data.get("pending_codes", {}).get(uid)
        now     = time.time()

        # Second click — valid code waiting → open modal
        if pending and (now - pending["issued_at"]) < CODE_TTL:
            # Rate limit: don't allow re-sending within 60s
            time_since = now - pending["issued_at"]
            if time_since < CODE_RESEND_CD:
                return await interaction.response.send_modal(VerifyModal(self.bot))
            # Code still valid and past resend cooldown — open modal anyway
            return await interaction.response.send_modal(VerifyModal(self.bot))

        # Rate limit check on fresh requests
        if pending:
            time_since = now - pending["issued_at"]
            if time_since < CODE_RESEND_CD:
                remaining = int(CODE_RESEND_CD - time_since)
                return await self._ephemeral(
                    interaction,
                    f"⏱️ Please wait **{remaining}s** before requesting a new code.",
                )

        # Generate and send new code
        code = str(random.randint(1000, 9999))

        try:
            dm_emb = _build_code_dm_embed(self.bot, code, interaction.guild.name)
            await interaction.user.send(embed=dm_emb)
        except discord.Forbidden:
            emb = discord.Embed(
                title="❌  DMs Disabled",
                colour=discord.Colour(0xED4245),
            )
            emb.add_field(
                name="Fix this in 3 steps",
                value=(
                    "**1.** Open Discord Settings\n"
                    "**2.** Go to **Privacy & Safety**\n"
                    "**3.** Enable **Allow direct messages from server members**\n\n"
                    "Then click **Verify Me** again."
                ),
                inline=False,
            )
            return await self._ephemeral(interaction, "", embed=emb)
        except Exception:
            return await self._ephemeral(interaction, "❌ Failed to send your code. Please try again in a moment.")

        data.setdefault("pending_codes", {})
        data["pending_codes"][uid] = {"code": code, "issued_at": now}
        await self.store.write(data)

        emb = discord.Embed(
            title="📨  Code Sent",
            colour=discord.Colour(0xF9A826),
        )
        emb.add_field(
            name="Check your DMs",
            value=(
                "Your 4-digit code is in your DMs from this bot.\n\n"
                "**Click Verify Me again** to enter it.\n"
                "*Code expires in 10 minutes.*"
            ),
            inline=False,
        )
        await self._ephemeral(interaction, "", embed=emb)

    async def handle_verify_submit(self, interaction: discord.Interaction, user_answer: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this inside the server.", ephemeral=True)

        data = await self.store.read()
        uid  = str(interaction.user.id)

        pending = data.get("pending_codes", {}).get(uid)
        now     = time.time()

        if not pending:
            return await interaction.response.send_message(
                "❌ No pending code found. Click **Verify Me** to get a new code.", ephemeral=True
            )

        if (now - pending["issued_at"]) >= CODE_TTL:
            data["pending_codes"].pop(uid, None)
            await self.store.write(data)
            return await interaction.response.send_message(
                "❌ Your code expired. Click **Verify Me** again to get a new one.", ephemeral=True
            )

        if user_answer != pending["code"]:
            return await interaction.response.send_message(
                "❌ Incorrect code. Check your DMs and try again, or click **Verify Me** for a new code.",
                ephemeral=True,
            )

        # Correct — mark verified and clean up
        data.setdefault("verified", {})
        data["verified"][uid]  = True
        data["pending_codes"].pop(uid, None)
        await self.store.write(data)

        await log_action(
            self.bot,
            "User Verified",
            f"User: {interaction.user.mention} (`{interaction.user.id}`)\n"
            f"Passed DM code check.",
        )

        granted = await self._grant_member_role(interaction)
        if granted:
            role         = interaction.guild.get_role(self.member_role_id)
            role_mention = role.mention if role else "the member role"

            emb = discord.Embed(
                title="✅  Verification Complete",
                colour=discord.Colour(0x57F287),
                timestamp=datetime.now(timezone.utc),
            )
            emb.add_field(
                name="Access granted",
                value=f"You've been given {role_mention} — welcome to MangoMods! 🥭",
                inline=False,
            )
            emb.set_footer(text=f"MangoMods  •  {self.bot.config.website_url}")
            await self._ephemeral(interaction, "", embed=emb)

    # ── /setupverify ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="setupverify",
        description="Post or refresh the Rules and Verification panels (staff only).",
    )
    async def setupverify(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not any(r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id} for r in interaction.user.roles):
            return await interaction.response.send_message("Staff only.", ephemeral=True)
        if not self.rules_channel_id or not self.verify_channel_id:
            return await interaction.response.send_message(
                "Set `RULES_CHANNEL_ID` and `VERIFICATION_CHANNEL_ID` in .env", ephemeral=True
            )

        rules_ch = interaction.guild.get_channel(self.rules_channel_id)
        ver_ch   = interaction.guild.get_channel(self.verify_channel_id)

        if not isinstance(rules_ch, discord.TextChannel) or not isinstance(ver_ch, discord.TextChannel):
            return await interaction.response.send_message("Invalid channel IDs in .env.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        await rules_ch.send(embed=_build_rules_embed(self.bot, ver_ch.mention),   view=RulesView(self.bot))
        await ver_ch.send(embed=_build_verify_embed(self.bot, rules_ch.mention),  view=VerifyView(self.bot))

        await log_action(self.bot, "Verification Panels Posted", f"By {interaction.user.mention}")
        await interaction.followup.send("✅ Rules + Verification panels posted.", ephemeral=True)

    # ── /resetverification ────────────────────────────────────────────────────

    @app_commands.command(
        name="resetverification",
        description="Reset a member's verification state (staff only).",
    )
    @app_commands.describe(
        member="Member to reset",
        remove_role="Also remove their member role so they must re-verify (default: True)",
    )
    async def resetverification(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        remove_role: bool = True,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not any(r.id in {self.bot.config.staff_role_id, self.bot.config.owner_role_id} for r in interaction.user.roles):
            return await interaction.response.send_message("Staff only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        uid  = str(member.id)
        data = await self.store.read()

        was_verified = bool(data.get("verified", {}).get(uid))
        was_acked    = bool(data.get("acknowledged", {}).get(uid))
        had_code     = uid in data.get("pending_codes", {})

        # Wipe all state
        data.get("verified",      {}).pop(uid, None)
        data.get("acknowledged",  {}).pop(uid, None)
        data.get("pending_codes", {}).pop(uid, None)
        await self.store.write(data)

        # Remove member role if requested and they have it
        role_removed = False
        if remove_role and self.member_role_id:
            role = interaction.guild.get_role(self.member_role_id)
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Verification reset by {interaction.user}")
                    role_removed = True
                except Exception:
                    pass

        await log_action(
            self.bot,
            "Verification Reset",
            f"Staff: {interaction.user.mention}\n"
            f"User: {member.mention} (`{member.id}`)\n"
            f"Was verified: **{was_verified}** | Had ack: **{was_acked}** | Had pending code: **{had_code}**\n"
            f"Member role removed: **{role_removed}**",
        )

        lines = [f"✅ Verification reset for {member.mention}."]
        if role_removed:
            lines.append("🔑 Member role removed — they must re-verify to regain access.")
        elif remove_role and not role_removed:
            lines.append("ℹ️ Member role was not present (nothing to remove).")
        else:
            lines.append("ℹ️ Member role was kept (remove_role=False).")

        lines.append("\nThey can now go through the verification flow from scratch.")
        await interaction.followup.send("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
