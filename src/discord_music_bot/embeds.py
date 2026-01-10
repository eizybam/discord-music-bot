from discord import Embed

def get_youtube_embed(title: str, url: str, thumbnail_url: str, duration: str, requester: str, channel: str, channel_url: str) -> Embed:
    embed = Embed(
        title=title,
        url=url,
        color=0xFF0000  # Youtube red
    )
    embed.set_thumbnail(url=thumbnail_url)
    embed.set_author(name=channel, url=channel_url)
    embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Requested by", value=requester, inline=True)
    return embed
