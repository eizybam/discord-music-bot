class PlaylistError(Exception):
    """Base exception for playlist-related errors."""


class TrackNotFoundError(PlaylistError):
    """Raised when a requested track or search result is not found."""


class FileCleanupError(Exception):
    """Raised when cleanup of a temporary file fails after retries."""


class YTDLError(Exception):
    """Raised for errors coming from yt-dlp operations."""
