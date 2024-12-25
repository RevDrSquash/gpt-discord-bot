from __future__ import annotations

import os

import logging
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from src.constants import (
    OWNER_USERID,
)

logger = logging.getLogger(__name__)

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sync")
    async def sync(self, int: discord.Interaction):
        """Force sync this bot's command tree"""
        try:
            if int.user.id == OWNER_USERID:
                synced = await self.bot.tree.sync()
                logger.info(synced)
                await int.response.send_message('Command tree synced.')
            else:
                await int.response.send_message('You must be the owner to use this command!')

        except Exception as e:
            logger.exception(e)
            await int.response.send_message(f"Failed to sync commands {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))
