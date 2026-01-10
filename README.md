# Discord Music Bot 

A powerful and feature-rich Discord bot that brings YouTube music streaming directly to your Discord server. Built with Python using discord.py and yt-dlp for reliable music playback.

## Features 

-  **Music Playback**: Stream songs from YouTube with high-quality audio
-  **Playlist Management**: Create and manage personal and server-wide playlists
-  **Smart Queuing**: Advanced queue system with song preloading for seamless playback
-  **Private Playlists**: Create personal playlists only you can access
-  **Comprehensive Logging**: Detailed logs for debugging and monitoring
-  **Async/Concurrent**: Built with async/await for optimal performance
-  **Slash Commands**: Modern Discord slash commands interface

## Requirements

### System Requirements
- **Python**: 3.8 or higher
- **FFmpeg**: Required for audio encoding (Opus format)
  - Download from: https://ffmpeg.org/download.html

### Python Dependencies
See `requirements.txt` for complete list:
- `discord.py>=2.3.2` - Discord API wrapper
- `yt-dlp>=2024.1.1` - YouTube downloader
- `python-dotenv>=1.0.0` - Environment variable management
- `filelock>=3.13.1` - File locking for safe concurrent access

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/discord-music-bot.git
cd discord-music-bot
```

### 2. Set Up Python Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Download and Setup FFmpeg
- **Windows**: Download from https://ffmpeg.org/download.html and extract to `bin/ffmpeg/`
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt-get install ffmpeg`

Ensure the `ffmpeg.exe` (Windows) or `ffmpeg` (Unix) is accessible at the path specified in `.env`

### 5. Configure Environment Variables
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your Discord bot token
# DISCORD_TOKEN=your_token_here
```

### 6. Create Discord Application
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Go to "Bot" section and click "Add Bot"
4. Copy the token and paste it in `.env` as `DISCORD_TOKEN`
5. Enable these **Privileged Gateway Intents**:
   - Message Content Intent
   - Server Members Intent
6. Go to OAuth2 → URL Generator, select:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Connect`, `Speak`, `Use Voice Activation`, `Manage Messages`
7. Use the generated URL to invite the bot to your server

### 7. Run the Bot
```bash
python -m src.discord_music_bot.main
```

## Usage

### Music Commands

#### `/play <song>`
Search for a song on YouTube and add it to the queue.
```
/play Never Gonna Give You Up Rick Astley
```

#### `/skip`
Skip the currently playing song and play the next one in queue.
```
/skip
```

#### `/pause`
Pause the current song.
```
/pause
```

#### `/resume`
Resume the paused song.
```
/resume
```

#### `/exit`
Disconnect the bot from the voice channel.
```
/exit
```

#### `/playlist <playlist_name>`
Play all songs from a playlist.
```
/playlist myfavorites
/playlist liked_songs_
```
(Use `_` suffix for private playlists)

### Playlist Commands

#### `/create <playlist_name> [private:true/false]`
Create a new playlist.
```
/create workout_mix private:false
/create my_songs private:true
```

#### `/add <song> <playlist>`
Add a song to a playlist.
```
/add "Bohemian Rhapsody Queen" workout_mix
```

#### `/remove <playlist> <song>`
Remove a song from a playlist.
```
/remove workout_mix "Another One Bites the Dust Queen"
```

## Project Structure

```
discord-music-bot/
├── main.py              # Bot entry point and setup
├── player_cog.py        # Music playback functionality
├── playlist_cog.py      # Playlist management
├── utils.py             # Utility functions (search, cleanup, etc.)
├── errors.py            # Custom exception classes
├── embeds_.py           # Discord embed templates
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variables template
├── .gitignore           # Git ignore file
├── data/
│   ├── logs/            # Bot logs
│   ├── playlists/       # Playlist JSON files
│   └── .cache/          # Temporary audio files
└── bin/
    └── ffmpeg/          # FFmpeg installation (Windows only)
```

## Configuration

### Environment Variables
Edit `.env` file to configure:

```env
DISCORD_TOKEN=your_bot_token_here          # Required: Your Discord bot token
PLAYLISTS_PATH=data/playlists/             # Path for playlist storage
CACHE_PATH=data/.cache/                    # Path for audio cache
FFMPEG_PATH=bin/ffmpeg/                    # Path to FFmpeg binary
LOG_DIR=data/logs                          # Path for log files
```

### Logging
- **Console Output**: INFO level and above
- **File Output**: DEBUG level and above (5MB rotating files)
- Logs stored in: `data/logs/bot.log`

## Features in Detail

### Smart Preloading
The bot preloads the next song in queue while the current song plays, enabling instant playback transitions.

### Concurrent Safety
Uses per-guild locks and async/await patterns to safely handle multiple users and commands simultaneously.

### Playlist Persistence
Playlists are stored as JSON files per guild, with support for both public and private playlists.

### File Management
Automatically manages temporary audio files with retry logic and cleanup scheduling.

## Troubleshooting

### Bot Not Responding
- Ensure the bot has permissions in the voice channel
- Check that the bot token is valid in `.env`
- Verify FFmpeg is installed and path is correct

### Audio Quality Issues
- Check FFmpeg installation
- Ensure internet connection is stable
- Try skipping and playing another song

### Playlist Not Found
- Verify playlist name is correct (case-sensitive)
- Use `_` suffix for private playlists
- Ensure the playlist is not empty

### Permission Errors
- Grant the bot these permissions: Send Messages, Connect, Speak
- Ensure the bot role is above other roles that might restrict it

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature suggestions.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For issues, questions, or suggestions, please open an issue on GitHub.

---

**Made with ❤️ for Discord music lovers**
