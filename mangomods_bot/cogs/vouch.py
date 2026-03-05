from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, Dict

import discord
from discord import app_commands
from discord.ext import commands

from mangomods_bot.storage import JSONStore
from mangomods_bot.utils.embeds import brand_color
from mangomods_bot.utils.log import log_action

import os

def _norm_name(s: str) -> str:
    return "".join(ch.lower() for ch in (s or "").strip() if ch.isalnum())

def resolve_seller_id(raw: str) -> int | None:
    """
    Accepts Mango/J4 (with light aliasing) and returns the user ID.
    """
    mango_id = int(os.getenv("VOUCH_SELLER_MANGO_ID", "0") or "0")
    j4_id = int(os.getenv("VOUCH_SELLER_J4_ID", "0") or "0")

    key = _norm_name(raw)

    mango_aliases = {"mango", "mangoclanker", "mangomods", "mangomod"}
    j4_aliases = {"j4", "jay4", "jfour"}

    if key in mango_aliases:
        return mango_id if mango_id else None
    if key in j4_aliases:
        return j4_id if j4_id else None
    return None

PRICE_RE = re.compile(r"^\s*\$?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*$")

class VouchLinksView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Website", style=discord.ButtonStyle.link, url="https://mangomods.store"))
        self.add_item(discord.ui.Button(label="Ticket Channel", style=discord.ButtonStyle.link, url="https://discord.com/channels/1375602951384469586/1376587073707966535"))

def fmt_price(raw: str) -> Optional[str]:
    m = PRICE_RE.match(raw or "")
    if not m:
        return None
    val = float(m.group(1))
    return f"${int(val)}" if val.is_integer() else f"${val:.2f}"


def rel_time(dt: datetime) -> str:
    return f"<t:{int(dt.timestamp())}:R>"


def get_custom_emoji(guild: discord.Guild, emoji_id: int, fallback: str) -> str:
    if not emoji_id:
        return fallback
    e = discord.utils.get(guild.emojis, id=emoji_id)
    return str(e) if e else fallback


def stars(n: int, star_emoji: str) -> str:
    n = max(1, min(5, n))
    return star_emoji * n


class VouchModal(discord.ui.Modal, title="New Vouch"):
    product = discord.ui.TextInput(
        label="Product",
        placeholder="e.g. Aegis CODM / Fluorite FF / Cert",
        max_length=60,
        required=True,
    )
    price = discord.ui.TextInput(
        label="Price",
        placeholder="e.g. 19 or $19.99",
        max_length=12,
        required=True,
    )
    seller = discord.ui.TextInput(
        label="Seller",
        placeholder="Mango Or J4",
        max_length=80,
        required=True,
    )
    rating = discord.ui.TextInput(
        label="Rating (1-5)",
        placeholder="5",
        max_length=1,
        required=True,
    )
    reason = discord.ui.TextInput(
        label="Reason (optional)",
        placeholder="Short review…",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    def __init__(self, bot: commands.Bot, post_channel_id: int):
        super().__init__()
        self.bot = bot
        self.post_channel_id = post_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        cog = self.bot.get_cog("Vouch")
        if not cog:
            return await interaction.response.send_message("Vouch system is not loaded.", ephemeral=True)
        await cog.create_vouch(interaction, self)


class Vouch(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.store = JSONStore("/data/vouches.json", {"next_id": 10000, "vouches": []})

    def _emoji_ids(self) -> Dict[str, int]:
        import os

        def i(name: str) -> int:
            try:
                return int(os.getenv(name, "0") or "0")
            except Exception:
                return 0

        return {
            "mango": i("VOUCH_EMOJI_MANGO_ID"),
            "tag": i("VOUCH_EMOJI_TAG_ID"),
            "money": i("VOUCH_EMOJI_MONEY_ID"),
            "seller": i("VOUCH_EMOJI_SELLER_ID"),
            "star": i("VOUCH_EMOJI_STAR_ID"),
            "note": i("VOUCH_EMOJI_NOTE_ID"),

            # NEW
            "line": i("VOUCH_EMOJI_LINE_ID"),

            # OPTIONAL bottom-row icons
            "vouched_by": i("VOUCH_EMOJI_VOUCHED_BY_ID"),
            "vouch_id": i("VOUCH_EMOJI_VOUCH_ID_ID"),
            "timestamp": i("VOUCH_EMOJI_TIMESTAMP_ID"),
        }

    async def _next_id(self) -> int:
        data = await self.store.read()
        n = int(data.get("next_id", 10000))
        data["next_id"] = n + 1
        await self.store.write(data)
        return n

    @app_commands.command(name="vouch", description="Post a vouch/review (MangoMods).")
    async def vouch(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        await interaction.response.send_modal(VouchModal(self.bot, post_channel_id=interaction.channel_id))

    async def create_vouch(self, interaction: discord.Interaction, modal: VouchModal):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        price = fmt_price(str(modal.price).strip())
        if not price:
            return await interaction.followup.send("Invalid price. Examples: `19`, `$19`, `19.99`.", ephemeral=True)

        try:
            rating_val = int(str(modal.rating).strip())
        except Exception:
            return await interaction.followup.send("Rating must be a number 1-5.", ephemeral=True)

        if rating_val < 1 or rating_val > 5:
            return await interaction.followup.send("Rating must be between 1 and 5.", ephemeral=True)

        product = str(modal.product).strip()
        seller_raw = str(modal.seller).strip()
        seller_id = resolve_seller_id(seller_raw)
        if not seller_id:
            return await interaction.followup.send(
                "Seller must be **Mango** or **J4** (exact name).",
                ephemeral=True
            )

        seller = f"<@{seller_id}>"
        reason = str(modal.reason).strip() if str(modal.reason).strip() else "No reason provided."

        vouch_id = await self._next_id()
        now = datetime.now(timezone.utc)

        # Save record
        data = await self.store.read()
        data.setdefault("vouches", [])
        data["vouches"].append({
            "id": vouch_id,
            "product": product,
            "price": price,
            "seller": seller,
            "rating": rating_val,
            "reason": reason,
            "vouched_by_id": interaction.user.id,
            "created_at": now.isoformat(),
        })
        await self.store.write(data)

        ids = self._emoji_ids()

        mango = get_custom_emoji(interaction.guild, ids["mango"], "🥭")
        tag = get_custom_emoji(interaction.guild, ids["tag"], "🏷️")
        money = get_custom_emoji(interaction.guild, ids["money"], "💲")
        seller_e = get_custom_emoji(interaction.guild, ids["seller"], "👤")
        star_e = get_custom_emoji(interaction.guild, ids["star"], "⭐")
        note = get_custom_emoji(interaction.guild, ids["note"], "📝")

        # NEW line connector
        line = get_custom_emoji(interaction.guild, ids["line"], "↳")

        # Optional bottom icons
        vouched_by_e = get_custom_emoji(interaction.guild, ids["vouched_by"], "🧑")
        vouch_id_e = get_custom_emoji(interaction.guild, ids["vouch_id"], "🆔")
        timestamp_e = get_custom_emoji(interaction.guild, ids["timestamp"], "🕒")

        # Embed formatted like your screenshot
        emb = discord.Embed(
            title=f"{mango} New Vouch Recorded!",
            colour=brand_color(self.bot),
            timestamp=now,
        )

        # Main rows (label on one line, value on next line with connector)
        emb.add_field(name=f"{tag} Product", value=f"{line} {product}", inline=True)
        emb.add_field(name=f"{money} Price", value=f"{line} {price.replace('$','')}", inline=True)

        emb.add_field(name=f"{seller_e} Seller", value=f"{line} {seller}", inline=False)
        emb.add_field(name=f"{star_e} Rating", value=f"{line} {stars(rating_val, star_emoji=star_e)}", inline=False)
        emb.add_field(name=f"{note} Reason", value=f"{line} {reason}", inline=False)

        # Bottom row (3 columns like screenshot)
        emb.add_field(name=f"{vouched_by_e} Vouched By", value=f"{line} {interaction.user.mention}", inline=True)
        emb.add_field(name=f"{vouch_id_e} Vouch ID", value=f"{line} {vouch_id}", inline=True)
        emb.add_field(name=f"{timestamp_e} Timestamp", value=f"{line} {rel_time(now)}", inline=True)

        emb.set_footer(text=f"{self.bot.config.website_url} • Vouches • {now.strftime('%-m/%-d/%y, %-I:%M %p')}")

        ch = interaction.guild.get_channel(modal.post_channel_id)
        if not isinstance(ch, discord.TextChannel):
            return await interaction.followup.send("Saved vouch, but couldn't find the channel to post in.", ephemeral=True)

        await ch.send(embed=emb, view=VouchLinksView())

        await log_action(
            self.bot,
            "Vouch Created",
            f"By {interaction.user.mention}\nID: **{vouch_id}**\nProduct: **{product}**\nSeller: **{seller}**\nRating: **{rating_val}**"
        )

        await interaction.followup.send("✅ Vouch posted!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Vouch(bot))