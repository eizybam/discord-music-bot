import asyncio
from asyncio import run_coroutine_threadsafe
from collections import deque
import json
import os
import logging

import discord
from discord import app_commands
from discord.ext import commands

from typing import Any, cast

from ..utils import process_search, autocomplete_playlist, fix_playlist_input, schedule_file_cleanup, seconds_to_ms
from ..errors import YTDLError

from ..embeds import get_youtube_embed

logger = logging.getLogger('discord_music_bot')


class PlayerCog(commands.Cog):
    def __init__(self, bot, playlists_path, cache_path, ffmpeg_path):
        self.bot = bot

        self.SONG_QUEUES = {}
        self.QUERIES_QUEUES = {}

        self.preloaded_songs = {}
        self.current_query = {}
        self.currently_playing = {}
        self.current_cache_filepath = {}

        self.playlists_path = playlists_path
        self.cache_path = cache_path
        # Normalize ffmpeg_path to handle different path formats reliably
        self.ffmpeg_path = os.path.normpath(ffmpeg_path).rstrip(os.sep)


        self.is_playing = {}
        self.can_play = {} #Avoids concurrency issues when users initialize "/play" at the same time, causing to start the bot multiple times.

        os.makedirs(self.cache_path, exist_ok=True)

        self.YDL_OPTIONS = {'extractor_args': {'youtube': {'player_client': ['default','web_safari'], 'player_js_version': ['actual']}},
                   'format': 'bestaudio/best',
                   'format_sort': ['abr:96'],
                   #'logger': logger,
                   'restrictfilenames': True,
                   'no_warnings': False,
                   'quiet': True,
                   'playlist_items': ':1',
                            'outtmpl': f'{self.cache_path}%(title)s - %(id)s.%(ext)s',
                            "ffmpeg_location": rf"{self.ffmpeg_path}",

                   'postprocessors': [{'key': 'FFmpegExtractAudio',
                                       'nopostoverwrites': False,
                                       'preferredcodec': 'opus',
                                       'preferredquality': '5'}]}
        self.FFMPEG_OPTIONS = {
                #"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                "options": "-vn -c:a libopus -b:a 96k",
            }

        self.can_skip = {}
        # per-guild locks to serialize access to queue/state for each guild
        self.guild_locks = {}

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            logger.info("PlayerCog ready on %s", guild_id)
            self.can_skip[guild_id] = True
    
    async def cog_unload(self):
        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            if guild_id in self.current_cache_filepath and self.current_cache_filepath[guild_id]:
                try:
                    schedule_file_cleanup(self.current_cache_filepath[guild_id])
                except Exception:
                    logger.exception("Failed to schedule cleanup for %s", self.current_cache_filepath[guild_id])

    async def _preload_next_song(self, guild_id: str):
        """Downloads next song in query"""
        # Checks if query queue has songs. Use a per-guild lock to serialize access.
        lock = self.guild_locks.setdefault(guild_id, asyncio.Lock())

        # Acquire lock only for quick checks and state updates; do long-running downloads outside lock
        async with lock:
            if not (guild_id in self.QUERIES_QUEUES and len(self.QUERIES_QUEUES[guild_id]) > 0):
                return
            next_query = self.QUERIES_QUEUES[guild_id][0]

            # Don't preload if next query is the same that the one that is currently playing.
            if guild_id in self.current_query and next_query == self.current_query[guild_id]:
                logger.debug("Song already preloaded.")
                return

            logger.info("Pre-loading: %s", next_query)
            # mark as busy for skipping
            self.can_skip[guild_id] = False

        # perform download outside the lock
        try:
            audio_url, title = await process_search(self.YDL_OPTIONS, next_query)

            if audio_url is None:
                async with lock:
                    self.can_skip[guild_id] = True
                return

            async with lock:
                if guild_id not in self.preloaded_songs:
                    self.preloaded_songs[guild_id] = {}

                self.preloaded_songs[guild_id][next_query] = (audio_url, title)
                logger.info("Preloaded song: '%s'", title)

        except YTDLError as e:
            logger.warning("YTDLError while preloading %s: %s", next_query, e)
        except Exception as e:
            logger.exception("Error while preloading %s: %s", next_query, e)
        finally:
            async with lock:
                self.can_skip[guild_id] = True

    @app_commands.command(name="playlist", description="Play songs from your playlist")
    async def play_from_playlist(self, interaction: discord.Interaction, playlist_name: str):
        await interaction.response.defer()

        voice_client = interaction.guild.voice_client
        guild_id = str(interaction.guild.id)

        if voice_client is None:
            if interaction.user.voice:
                voice_client = await interaction.user.voice.channel.connect()
            else:
                await interaction.followup.send("You are not connected to a voice channel.")
                if guild_id in self.QUERIES_QUEUES:
                    self.QUERIES_QUEUES[guild_id].clear()
                return
        
        playlist_file = os.path.join(self.playlists_path, f"{guild_id}.json")
        if not os.path.exists(playlist_file):
            await interaction.followup.send("No playlists found for this server.")
            return

        try:
            with open(playlist_file, "r", encoding='utf-8') as f:
                playlists = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.exception("Failed to load playlist file %s: %s", playlist_file, e)
            await interaction.followup.send("Error reading playlists. Please try again later.")
            return

        playlist, playlist_type = fix_playlist_input(str(interaction.user.id), playlist_name)

        if playlist not in playlists[playlist_type]:
            await interaction.followup.send("Playlist does not exist.")
            return

        if not playlists[playlist_type][playlist]:
            await interaction.followup.send("Playlist is empty.")
            return

        lock = self.guild_locks.setdefault(guild_id, asyncio.Lock())

        async with lock:
            if guild_id not in self.QUERIES_QUEUES:
                self.QUERIES_QUEUES[guild_id] = deque()

            self.QUERIES_QUEUES[guild_id].extend(playlists[playlist_type][playlist])

        await interaction.followup.send(f"{len(playlists[playlist_type][playlist])} songs added to the queue.")

        if not (voice_client and voice_client.is_playing()):
            await self.play_next_song(interaction)

    @play_from_playlist.autocomplete('playlist_name')
    async def autocomplete_callback_add(self, interaction: discord.Interaction, current: str) -> list[
        app_commands.Choice[str]]:
        return autocomplete_playlist(self.playlists_path, interaction, current)

    @app_commands.command(name="play", description="Search for a song and add it to the queue.")
    async def play(self, interaction, song: str):
        await interaction.response.defer()

        voice_client = interaction.guild.voice_client
        guild_id = str(interaction.guild.id)

        if voice_client is None:
            if interaction.user.voice:
                voice_client = await interaction.user.voice.channel.connect()
            else:
                await interaction.followup.send("You are not connected to a voice channel.")
                if guild_id in self.QUERIES_QUEUES:
                    self.QUERIES_QUEUES[guild_id].clear()
                return

        lock = self.guild_locks.setdefault(guild_id, asyncio.Lock())

        async with lock:
            if guild_id not in self.QUERIES_QUEUES:
                self.QUERIES_QUEUES[guild_id] = deque()

            # ensure we reference the correct queue dict
            self.QUERIES_QUEUES[guild_id].append(song)

            # mark play state under lock
            if not (voice_client and voice_client.is_playing()):
                self.can_play[guild_id] = False

        if not (voice_client and voice_client.is_playing()):
            await interaction.followup.send(f"{song} added to the queue")
            await self.play_next_song(interaction)
        else:
            await interaction.followup.send(f"{song} added to the queue")

    async def play_next_song(self, interaction):
        """Plays current song and preloads next in queue"""
        guild_id = str(interaction.guild.id)
        voice_client = interaction.guild.voice_client

        if self.QUERIES_QUEUES.get(guild_id):
            # Acquire per-guild lock to pop the next query and inspect cached state.
            lock = self.guild_locks.setdefault(guild_id, asyncio.Lock())

            async with lock:
                if not self.QUERIES_QUEUES.get(guild_id):
                    try:
                        await voice_client.disconnect()
                    except Exception:
                        pass
                    return

                query = self.QUERIES_QUEUES[guild_id].popleft()

                filepath, title, thumbnail, duration, original_url, requester, channel, channel_url = (None, None, None, 0, None, "Unknown", "Unknown", "Unknown")

                if guild_id in self.current_query and self.current_query[guild_id] == query:
                    logger.debug("CURRENTLY PLAYING SONG MATCHES WITH QUERY")
                    title = self.currently_playing[guild_id].get("title", "Untitled")
                    filepath = self.currently_playing[guild_id].get("filepath", None)
                    thumbnail = self.currently_playing[guild_id].get("thumbnail", "")
                    duration = self.currently_playing[guild_id].get("duration", 0)
                    original_url = self.currently_playing[guild_id].get("original_url", "")
                    requester = self.currently_playing[guild_id].get("requester", "Unknown")
                    channel = self.currently_playing[guild_id].get("channel", "Unknown")
                    channel_url = self.currently_playing[guild_id].get("channel_url", "Unknown")

                    need_download = False

                elif guild_id in self.preloaded_songs and query in self.preloaded_songs[guild_id]:
                    filepath, title = self.preloaded_songs[guild_id].pop(query)
                    logger.info("Playing from cache: %s", title)
                    need_download = False
                else:
                    need_download = True

            # perform download outside the lock
            if need_download:
                logger.info("Downloading: %s", query)
                try:
                    filepath, track_info = await process_search(self.YDL_OPTIONS, query)
                    title = track_info.get("title", "Untitled")
                    thumbnail = track_info.get("thumbnail", "")
                    duration = seconds_to_ms(track_info.get("duration", 0))
                    original_url = track_info.get("original_url", "")
                    channel = track_info.get("channel", "Unknown")
                    channel_url = track_info.get("channel_url", "Unknown")
                    requester = interaction.user.name
                    
                    logger.info("Downloaded: %s (Duration: %s)", title, duration)
                except YTDLError as e:
                    logger.warning("YTDLError while processing %s: %s", query, e)
                    await interaction.channel.send(f"Error processing '{query}': {e}")
                    asyncio.create_task(self.play_next_song(interaction))
                    return
                except Exception as e:
                    logger.exception("Unexpected error while processing %s: %s", query, e)
                    await interaction.channel.send(f"Error processing '{query}': {e}")
                    asyncio.create_task(self.play_next_song(interaction))
                    return

            # store current cache filepath and playing info under lock
            async with lock:
                self.current_cache_filepath[guild_id] = filepath
                self.current_query[guild_id] = query
                self.currently_playing[guild_id] = {"title": title, "filepath": filepath, "thumbnail": thumbnail, "duration": duration,
                                                    "original_url": original_url, "requester": requester, 
                                                    "channel": channel, "channel_url": channel_url}

            if filepath is None:
                logger.error("No filepath available for query '%s', skipping.", query)
                asyncio.create_task(self.play_next_song(interaction))
                return

            ffmpeg_opts = cast(dict[str, Any], self.FFMPEG_OPTIONS)
            source = discord.FFmpegOpusAudio(filepath, **ffmpeg_opts,
                                             executable=os.path.join(self.ffmpeg_path, "ffmpeg.exe"))

            def after_play(error):
                if error:
                    logger.exception("Error playing %s: %s", title, error)

                async def _after_play():
                    async with lock:
                        try:
                            next_item = None
                            if self.QUERIES_QUEUES.get(guild_id):
                                next_item = self.QUERIES_QUEUES[guild_id][0]

                            if filepath and (not self.QUERIES_QUEUES.get(guild_id) or self.current_query.get(guild_id) != next_item):
                                # schedule centralized cleanup
                                try:
                                    schedule_file_cleanup(filepath)
                                except Exception:
                                    logger.exception("Failed to schedule centralized cleanup for %s", filepath)
                        except Exception:
                            logger.exception("Error during after_play cleanup check for %s", filepath)

                    try:
                        await self.play_next_song(interaction)
                    except Exception:
                        logger.exception("Error scheduling next song for guild %s", guild_id)

                try:
                    run_coroutine_threadsafe(_after_play(), self.bot.loop)
                except Exception:
                    logger.exception("Error scheduling after_play coroutine for guild %s", guild_id)

            voice_client.play(source, after=after_play)

            try:
                embed = get_youtube_embed(title=title, url=original_url, thumbnail_url=thumbnail,
                                        duration=duration, requester=requester, channel=channel, channel_url=channel_url)

                await interaction.channel.send(embed=embed)
                logger.info("Sent embed for currently playing song: %s in guild %s", title, guild_id)
            except Exception:
                logger.exception("Failed to send embed for currently playing song: %s in guild %s", title, guild_id)

            asyncio.create_task(self._preload_next_song(guild_id))
        else:
            await voice_client.disconnect()

    @app_commands.command(name="skip", description="Skips current song to play the next one in the queue")
    async def skip(self, interaction):
        await interaction.response.defer()

        if not self.can_skip[str(interaction.guild.id)]:
            await interaction.followup.send(f"Please wait for the next song to be added to the queue.")
            return

        if interaction.guild.voice_client and (
                interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
            interaction.guild.voice_client.stop()
            await interaction.followup.send("Skipped the current song.")
        else:
            await interaction.followup.send("Not playing anything...")

    @app_commands.command(name="exit", description="Disconnects the bot from the voice channel")
    async def exit(self, interaction):
        await interaction.response.defer()

        if interaction.user.voice is None:
            await interaction.followup.send("You are not connected to a voice channel.")
            return

        if interaction.guild.voice_client is None:
            await interaction.followup.send("Bot is already suspended.")
            return

        await interaction.followup.send("Going to sleep... zzz")
        await interaction.guild.voice_client.disconnect()

    @app_commands.command(name="pause", description="Pauses the current song.")
    async def pause(self, interaction):
        await interaction.response.defer()
        if interaction.user.voice is None:
            await interaction.followup.send("You are not connected to a voice channel.")
            return

        if interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.followup.send("Paused the current song.")

        elif not interaction.guild.voice_client.is_playing():
            await interaction.followup.send("The song is already paused.")
        return

    @app_commands.command(name="resume", description="Resumes the current song.")
    async def resume(self, interaction):
        await interaction.response.defer()

        if interaction.user.voice is None:
            await interaction.followup.send("You are not connected to a voice channel.")
            return

        if interaction.guild.voice_client is None:
            await interaction.followup.send("Bot is not in a voice channel.")
            return

        if not interaction.guild.voice_client.is_playing():
            await interaction.followup.send("Resuming song")
            interaction.guild.voice_client.resume()
            return
