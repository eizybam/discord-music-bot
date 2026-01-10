import asyncio
import os
import sys
import traceback
import logging
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

from dotenv import load_dotenv, find_dotenv

from .cogs.player_cog import PlayerCog
from .cogs.playlist_cog import PlaylistCog

dotenv_path = find_dotenv()
load_dotenv(dotenv_path)

TOKEN = os.getenv("DISCORD_TOKEN")
PLAYLISTS_PATH = os.getenv("PLAYLISTS_PATH", "data/playlists/")
CACHE_PATH = os.getenv("CACHE_PATH", "data/.cache/")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "bin/ffmpeg/")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables.")

# --- Logging configuration ---
LOG_DIR = os.getenv("LOG_DIR", "data/logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger = logging.getLogger('discord_music_bot')
logger.setLevel(logging.DEBUG)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
ch.setFormatter(ch_formatter)
logger.addHandler(ch)

# Rotating file handler
fh = RotatingFileHandler(os.path.join(LOG_DIR, 'bot.log'), maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
fh.setFormatter(fh_formatter)
logger.addHandler(fh)
# ------------------------------

bot = commands.Bot(command_prefix='/', intents=discord.Intents.all())


@bot.event
async def on_command_error(ctx, error):
    logger.error("Error in command %s: %s", ctx.command, error, exc_info=error)
    # Also print a concise message to the user if possible
    try:
        await ctx.reply(f"An error occurred while processing the command: {type(error).__name__}: {error}")
    except Exception:
        # If replying fails, just log the traceback
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stdout)


@bot.event
async def on_ready():
    await bot.tree.sync()
    logger.info(f"Bot connected as {bot.user}")

@bot.event
async def on_disconnect():
    print("Bot disconnected.")
    logger.info("Bot disconnected.")

async def main():
    async with bot:
        await bot.add_cog(PlayerCog(bot, PLAYLISTS_PATH, CACHE_PATH, FFMPEG_PATH))
        await bot.add_cog(PlaylistCog(bot, PLAYLISTS_PATH))
        await bot.start(TOKEN) # type: ignore


if __name__ == '__main__':
    logger.info("Starting bot...")
    asyncio.run(main())
