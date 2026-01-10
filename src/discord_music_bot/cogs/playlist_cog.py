import discord
from discord import app_commands
from discord.ext import commands

import json
import os
import logging

from ..utils import manage_playlists, create_playlist, fix_playlist_input, autocomplete_playlist

logger = logging.getLogger('discord_music_bot')


class PlaylistCog(commands.Cog):
    def __init__(self, bot, playlists_path):
        self.bot = bot

        self.playlists = {}
        self.playlists_path = playlists_path
        self.can_skip = {}
        # ensure playlists directory exists and create files for existing guilds
        os.makedirs(self.playlists_path, exist_ok=True)
        for guild in getattr(self.bot, 'guilds', []):
            try:
                self._ensure_guild_file(str(guild.id))
            except Exception:
                logger.exception("Failed to ensure playlist file for guild %s", guild)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            logger.info("PlaylistCog ready on %s", guild_id)
            # make sure a playlist file exists for this guild
            try:
                self._ensure_guild_file(guild_id)
            except Exception:
                logger.exception("Failed to ensure playlist file on ready for %s", guild_id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Create a playlist file when the bot is added to a new guild."""
        try:
            self._ensure_guild_file(str(guild.id))
        except Exception:
            logger.exception("Failed to create playlist file for new guild %s", guild.id)

    def _ensure_guild_file(self, guild_id: str):
        """Ensure the JSON file for a guild exists with default structure."""
        path = os.path.join(self.playlists_path, f"{guild_id}.json")
        if not os.path.exists(path):
            # create a default structure with an empty public playlists mapping
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({"public": {}}, f, ensure_ascii=False, indent=2)
            logger.info("Created playlist file for new guild %s", guild_id)

    @app_commands.command(name="create", description="Create a playlist")
    @app_commands.describe(private="True: Playlist can only be accessed by you")
    async def create(self, interaction, playlist_name: str, private: bool = False):
        guild_id = str(interaction.guild.id)

        await interaction.response.defer()

        if "_" in playlist_name:
            await interaction.followup.send("No underscore allowed.")
            return

        if private:
            playlist_type = str(interaction.user.id)
        else:
            playlist_type = "public"

        try:
            await manage_playlists(self.playlists_path, guild_id,
                                   lambda playlists:
                                   create_playlist(playlists, playlist_type, playlist_name))
        except Exception:
            logger.exception("Failed creating playlist %s for guild %s", playlist_name, guild_id)
            await interaction.followup.send("Failed to create playlist. Try again later.")
            return

        await interaction.followup.send(f"Playlist {playlist_name} created successfully.")

    @app_commands.command(name="add", description="Add a song to a playlist")
    async def add(self, interaction, song: str, playlist: str):
        guild_id = str(interaction.guild.id)
        await interaction.response.defer()

        playlist_input_fixed, playlist_type = fix_playlist_input(str(interaction.user.id), playlist)

        try:

            await manage_playlists(self.playlists_path, guild_id,
                                   lambda playlists:
                                   playlists[playlist_type][playlist_input_fixed].append(song))

        except KeyError:
            await interaction.followup.send("Playlist does not exist.")

        except Exception:
            logger.exception("Failed to add song %s to playlist %s for guild %s", song, playlist, guild_id)
            await interaction.followup.send("Failed to add song. Try again later.")

        else:
            await interaction.followup.send("Song successfully added.")

    @add.autocomplete('playlist')
    async def autocomplete_callback_add(self, interaction: discord.Interaction, current: str) -> list[
        app_commands.Choice[str]]:
        return autocomplete_playlist(self.playlists_path, interaction, current)

    @commands.hybrid_command(name="remove", description='Remove a song from a playlist')
    async def remove_song(self, ctx: commands.Context, playlist: str, song: str):
        guild_id = str(ctx.guild.id) # type: ignore
        author = str(ctx.author.id)
        playlist_input_fixed, playlist_type = fix_playlist_input(author, playlist)

        try:
            await manage_playlists(self.playlists_path, guild_id,
                                   lambda playlists:
                                   playlists[playlist_type][playlist_input_fixed].remove(song))
        except KeyError:
            await ctx.reply(f"Playlist {playlist} not found.")

        except ValueError:
            await ctx.reply(f"Song {song} does not exist in playlist {playlist}.")

        except Exception:
            logger.exception("Failed to remove song %s from playlist %s for guild %s", song, playlist, guild_id)
            await ctx.reply("Failed to remove song. Try again later.")

        else:
            await ctx.reply(f"Song {song} successfully removed.")

    @remove_song.autocomplete("playlist")
    async def autocomplete_callback_remove_p(self, interaction: discord.Interaction, current: str) -> list[
        app_commands.Choice[str]]:
        return autocomplete_playlist(self.playlists_path, interaction, current)

    @remove_song.autocomplete("song")
    async def song_autocomplete(self, interaction: discord.Interaction, current: str):
        playlist_input = interaction.namespace.playlist

        try:
            with open(self.playlists_path + str(interaction.guild.id) + ".json", "r", encoding='utf-8') as f: # type: ignore
                playlists = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.exception("Failed to load playlist file for guild %s: %s", interaction.guild.id, e)
            return []

        if playlist_input.endswith("_"):
            songs_available = playlists[str(interaction.user.id)][playlist_input[:-1]]
        else:
            songs_available = playlists["public"][playlist_input]

        return [app_commands.Choice(name=song, value=song) for song in songs_available if
                current.lower() in song.lower()]
