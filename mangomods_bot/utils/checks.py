from __future__ import annotations

import discord
from discord import app_commands

def staff_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False

        bot = interaction.client
        staff_role_id = getattr(getattr(bot, "config", None), "staff_role_id", None)
        if not staff_role_id:
            return False

        return any(r.id == staff_role_id for r in interaction.user.roles)

    return app_commands.check(predicate)