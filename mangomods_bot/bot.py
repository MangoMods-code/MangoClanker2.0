from __future__ import annotations

import itertools
import logging

import discord
from discord.ext import commands, tasks

from mangomods_bot.config import load_config
from mangomods_bot.storage import JSONStore
from mangomods_bot.views.ticket_panel import TicketPanelView
from mangomods_bot.views.ticket_actions import TicketActionsView
import os
from mangomods_bot.cogs.verification import RulesView, VerifyView

log = logging.getLogger("mangomods")

PRESENCE_PRODUCTS_COUNT = "__PRODUCTS_COUNT__"
PRESENCE_TICKETS_COMPLETED = "__TICKETS_COMPLETED__"
PRESENCE_MEMBER_COUNT = "__MEMBER_COUNT__"


class MangoModsBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True  # human-only counting + join/leave updates

        super().__init__(
            command_prefix="!", # Not relavant for some reason
            intents=intents,
        )

        self.config = load_config()

        self.ticket_store = JSONStore(
            "/data/tickets.json",
            {
                "open_tickets_by_user": {},
                "ticket_cooldowns": {},
                "tickets_completed": 0,
            },
        )

        self.products_store = JSONStore(
            "/data/products.json",
            {
                "products": {},
                "meta": {"last_updated_by": None, "last_updated_at": None},
            },
        )

        self._presence_cycle: itertools.cycle[str] | None = None

    async def setup_hook(self) -> None:
        # Dev-mode: wipe global commands to prevent stale duplicates
        # Only do global wipe when you flip this to True manually (one-time cleanup)
        DO_GLOBAL_WIPE = False

        SYNC = os.getenv("SYNC_COMMANDS_ON_STARTUP", "0") == "1"
        if SYNC:
            guild_obj = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)

            

        # Persistent views
        self.add_view(TicketPanelView(self))

        # Register ticket action views for all states (so buttons always work after restarts)
        self.add_view(TicketActionsView(self, locked=False, closed=False))
        self.add_view(TicketActionsView(self, locked=True, closed=False))
        self.add_view(TicketActionsView(self, locked=False, closed=True))
        self.add_view(TicketActionsView(self, locked=True, closed=True))
        self.add_view(RulesView(self))
        self.add_view(VerifyView(self))

        # Load cogs
        await self.load_extension("mangomods_bot.cogs.tickets")
        await self.load_extension("mangomods_bot.cogs.status")
        await self.load_extension("mangomods_bot.cogs.admin")
        await self.load_extension("mangomods_bot.cogs.welcome")
        await self.load_extension("mangomods_bot.cogs.vouch")
        await self.load_extension("mangomods_bot.cogs.reviews_guard")
        await self.load_extension("mangomods_bot.cogs.mute")
        await self.load_extension("mangomods_bot.cogs.devtools")
        await self.load_extension("mangomods_bot.cogs.member_counter")
        await self.load_extension("mangomods_bot.cogs.control")
        await self.load_extension("mangomods_bot.cogs.milestones")
        await self.load_extension("mangomods_bot.cogs.temprole")
        await self.load_extension("mangomods_bot.cogs.verification")
        await self.load_extension("mangomods_bot.cogs.promos")
        await self.load_extension("mangomods_bot.cogs.sticky")
        await self.load_extension("mangomods_bot.cogs.updates")


        if self.config.guild_id:
            guild_obj = discord.Object(id=self.config.guild_id)

            # Fast sync: one call
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)

            log.info("Synced commands to guild %s (dev mode).", self.config.guild_id)
        else:
            await self.tree.sync()

        self.start_presence_rotation()

    def _primary_guild(self) -> discord.Guild | None:
        if self.config.guild_id:
            g = self.get_guild(self.config.guild_id)
            if g:
                return g
        return self.guilds[0] if self.guilds else None

    def start_presence_rotation(self) -> None:
        website = (
            self.config.website_url.replace("https://", "")
            .replace("http://", "")
            .strip("/")
            or "mangomods.store"
        )

        messages = [
            website,
            "🥭 Runs Off Mangos 🥭",
            PRESENCE_PRODUCTS_COUNT,
            PRESENCE_MEMBER_COUNT,
            PRESENCE_TICKETS_COMPLETED,
        ]
        self._presence_cycle = itertools.cycle(messages)

        if not self.presence_task.is_running():
            self.presence_task.start()

    @tasks.loop(seconds=30)
    async def presence_task(self):
        try:
            base = next(self._presence_cycle) if self._presence_cycle else "mangomods.store"

            if base == PRESENCE_TICKETS_COMPLETED:
                data = await self.ticket_store.read()
                completed = int(data.get("tickets_completed", 0))
                base = f"Tickets Completed: {completed}"

            elif base == PRESENCE_PRODUCTS_COUNT:
                data = await self.products_store.read()
                products = data.get("products", {}) if isinstance(data, dict) else {}
                count = len(products) if isinstance(products, dict) else 0
                base = f"Products Available: {count}"

            elif base == PRESENCE_MEMBER_COUNT:
                g = self._primary_guild()
                if g:
                    # humans only (exclude bots)
                    humans = sum(1 for m in g.members if not m.bot)
                    base = f"Supporting {humans} members"
                else:
                    base = "Supporting members"

            await self.change_presence(activity=discord.Game(name=str(base)))
        except Exception:
            return

    @presence_task.before_loop
    async def before_presence(self):
        await self.wait_until_ready()
        self.presence_task.change_interval(seconds=max(10, int(self.config.presence_rotate_seconds or 30)))

    async def on_ready(self) -> None:
        log.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "?")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        try:
            msg = "Something went wrong."
            if isinstance(error, discord.app_commands.MissingPermissions):
                msg = "You don’t have permission to use that."
            elif isinstance(error, discord.app_commands.CheckFailure):
                msg = "You can’t use that command."
            elif isinstance(error, discord.app_commands.CommandOnCooldown):
                msg = f"Slow down — try again in {error.retry_after:.1f}s."
            else:
                msg = f"Error: {error.__class__.__name__}"

            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            return
