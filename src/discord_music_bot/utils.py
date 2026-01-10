import asyncio
import json
import logging
import os

from discord import app_commands
from typing import Optional, Tuple

import yt_dlp
from filelock import AsyncFileLock

from .errors import YTDLError, FileCleanupError

# Use a project-wide logger name so main can configure handlers centrally
logger = logging.getLogger('discord_music_bot')

# --- centralized cleanup queue / worker ---
_cleanup_queue: asyncio.Queue[Tuple[str, int, int, int]] = asyncio.Queue()
_cleanup_worker_task: Optional[asyncio.Task] = None

async def _cleanup_worker():
    """Worker that serializes file deletions by consuming the cleanup queue."""
    while True:
        filepath, delay, max_attempts, retry_interval = await _cleanup_queue.get()
        try:
            await file_cleanup(filepath, delay=delay, max_attempts=max_attempts, retry_interval=retry_interval)
        except FileCleanupError as e:
            logger.warning("Central cleanup failed for %s: %s", filepath, e)
        except Exception:
            logger.exception("Unexpected error in cleanup worker for %s", filepath)
        finally:
            _cleanup_queue.task_done()

def schedule_file_cleanup(filepath: str, delay: int = 5, max_attempts: int = 3, retry_interval: int = 1):
    """
    Enqueue a file for cleanup. Starts the cleanup worker if needed.
    Non-blocking; safe to call from anywhere in the running event loop.
    """
    global _cleanup_worker_task
    loop = asyncio.get_running_loop()
    # start worker if not running
    if _cleanup_worker_task is None or _cleanup_worker_task.done():
        _cleanup_worker_task = loop.create_task(_cleanup_worker())
    _cleanup_queue.put_nowait((filepath, delay, max_attempts, retry_interval))

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extract, query, ydl_opts)


def _extract(query, ydl_opts):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            return info
    except Exception as e:
        logger.exception("yt-dlp extraction failed for query: %s", query)
        raise YTDLError(str(e)) from e


def add_song_to_playlist(playlist, playlist_type, song):
    playlist[playlist_type].append(song)

    return playlist


def fix_playlist_input(author: str, playlist_input: str):
    if playlist_input.endswith("_"):
        playlist_input = playlist_input[:-1]
        playlist_type = author
    else:
        playlist_type = "public"

    return playlist_input, playlist_type


def create_playlist(playlists, playlist_type, playlist_name):
    if playlist_type in playlists and playlist_name in playlists[playlist_type]:
        return

    if playlist_type not in playlists:
        playlists[playlist_type] = {}

    if playlist_name not in playlists[playlist_type]:
        playlists[playlist_type][playlist_name] = []


async def manage_playlists(playlists_path, guild_id, operation):
    playlist_file = f"{playlists_path}{guild_id}.json"

    async with AsyncFileLock(f"{playlist_file}.lock"):
        # This code block is protected by filelock, only one process and/or async task can execute this at a time
        with open(playlist_file, "r", encoding='utf-8') as f:
            playlists = json.load(f)

        operation(playlists)

        with open(playlist_file, "w", encoding='utf-8') as f:
            json.dump(playlists, f, ensure_ascii=False, indent=2)


def autocomplete_playlist(playlists_path, interaction, current):
    playlist_file = f"{playlists_path}{interaction.guild.id}.json"
    if not os.path.exists(playlist_file):
        return []

    try:
        with open(playlist_file, "r", encoding='utf-8') as f:
            playlists = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.exception("Failed to load playlist file %s: %s", playlist_file, e)
        return []

    public_playlists_available = list(playlists["public"].keys()) if playlists["public"] else []
    private_playlists_available = list(playlists[str(interaction.user.id)].keys()) if str(
        interaction.user.id) in playlists else []

    # Return a list of app_commands.Choice I use "_" to identify when a playlist is private for purposes of adding it in the function add
    return ([app_commands.Choice(name=playlist, value=playlist) for playlist in public_playlists_available if
             current.lower() in playlist.lower()] +
            [app_commands.Choice(name=playlist + " **private**", value=playlist + "_") for playlist in
             private_playlists_available if current.lower() in playlist.lower()])


async def file_cleanup(filepath: str, delay: int = 5, max_attempts: int = 3, retry_interval: int = 1):
    await asyncio.sleep(delay)

    for attempt in range(max_attempts):
        try:
            os.remove(filepath)
            logger.info("File removed: %s", filepath)
            return

        except PermissionError:
            logger.warning(
                "Attempt %s/%s: Couldn't remove '%s', file in use. Next attempt in %ss...",
                attempt + 1, max_attempts, os.path.basename(filepath), retry_interval)
            await asyncio.sleep(retry_interval)

        except FileNotFoundError:
            logger.info("File doesn't exist: %s", filepath)
            return

        except Exception as e:
            logger.exception("Unexpected error when removing %s: %s", filepath, e)
            return

    msg = f"Couldn't delete '{os.path.basename(filepath)}' after {max_attempts} attempts."
    logger.error(msg)
    raise FileCleanupError(msg)


async def process_search(ydl_options, next_query):
    results = await search_ytdlp_async(f"ytsearch1:{next_query}", ydl_options)
    tracks = results.get("entries", [])

    # IF SEARCH FAILED, OR NO SONG WAS FOUND.
    if len(tracks) == 0:
        return None, None

    first_track_info = tracks[0]

    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        base_filename = ydl.prepare_filename(first_track_info)

    root, ext = os.path.splitext(base_filename)

    final_filepath = root + ".opus"

    audio_url = final_filepath
    title = first_track_info.get("title", "Untitled")

    return audio_url, first_track_info

def seconds_to_ms(seconds: int) -> str:
    """Convert seconds to a mm:ss format string."""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02}"
