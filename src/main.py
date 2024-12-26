import logging
from pathlib import Path

import click

import discord
from discord.ext import commands

from src.constants import BOT_INVITE_URL, DISCORD_BOT_TOKEN, ADMIN_SERVER_ID

logging.basicConfig(
    format="[%(asctime)s] [%(filename)s:%(lineno)d] %(message)s", level=logging.INFO
)

class GPTBot(commands.Bot):
    sync_on_setup = False
    
    def __init__(self, intents: discord.Intents) -> None:
        super().__init__(command_prefix="/", intents=intents, help_command=None)

    async def setup_hook(self):
        # Enable cogs in discord_cogs directory (except for files starting with _)
        cog_dir = Path(__file__).parent / "discord_cogs"
        for cog_path in cog_dir.glob("*.py"):
            cog_name = cog_path.stem
            if cog_name.startswith("_"):
                continue
            await self.load_extension(f"src.discord_cogs.{cog_name}")
            
        if self.sync_on_setup:
            await self.sync_commands()

    async def on_ready(self):
        logging.info(f"We have logged in as {self.user}. Invite URL: {BOT_INVITE_URL}")
    
    async def sync_commands(self):
        synced_global = await self.tree.sync()
        logging.info(f"Synced {len(synced_global)} global commands.")
        
        synced_admin = await self.tree.sync(guild=discord.Object(id=ADMIN_SERVER_ID))
        logging.info(f"Synced {len(synced_admin)} admin commands.")

@click.command()
@click.option('--sync', '-s', default=False)
def main(sync):
    # Define intents
    intents = discord.Intents.default()
    intents.message_content = True

    # Create bot instance
    bot = GPTBot(intents=intents)
    bot.sync_on_setup = sync
    
    # Start the event loop
    bot.run(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    main()
