import discord.ext
from discord.ext import commands
from discord import app_commands
from helpers.streamersac import streamer_autocomplete
from dateutil import parser
from zoneinfo import ZoneInfo
from twitchAPI.helper import first
from twitchAPI.type import TwitchResourceNotFound
from helpers.constants import (
    is_whitelisted,
    get_cocoasguild,
    get_twitch
)
from psql import (
    fetch, 
    fetchrow, 
    execute, 
    fetchval,
    close_pool
)
from handlers.logger import logger

class TwitchCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="schedule", description="Get Cocoa's schedule.")
    @is_whitelisted()
    @app_commands.describe(twitch_username="Select a Twitch user from this server")
    @app_commands.autocomplete(twitch_username=streamer_autocomplete)
    async def schedule(self, interaction: discord.Interaction, twitch_username: str):
        await interaction.response.defer() 
        try:
            # get user if any
            twitch = get_twitch()
            user = await first(twitch.get_users(logins=[twitch_username]))
            if not user.id or not user.login:
                await interaction.followup.send("Twitch user not found.", ephemeral=True)
                return
            # get the first 5 segments of their stream schedule
            try:
                hit = await twitch.get_channel_stream_schedule(broadcaster_id=str(user.id), first=5)
            except TwitchResourceNotFound:
                await interaction.followup.send(f"{user.display_name} does not have a schedule.", ephemeral=False)
                return
            # If there's a schedule, iterate over each segment
            name = hit.data.broadcaster_name
            segments = hit.data.segments
            msg = ''
            if not segments:
                await interaction.followup.send(f"{user.display_name} has no segments in their schedule.", ephemeral=False)
                return
            # Timezone is not available to discord public API
            user_tz = await get_user_timezone(interaction.user.id)
            if user_tz is None:
                user_tz = "UTC"

            cocoasguild = get_cocoasguild()
            streamEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLicense") if cocoasguild else ''
            boba = discord.utils.get(cocoasguild.emojis, name="cocoaBoba") if cocoasguild else ''
            personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else ''
            # https://dev.twitch.tv/docs/api/reference/#get-channel-stream-schedule
            groups = {}
            for s in segments:
                # Parse datetime in state_time and end_time attributes (RFC 3339 format)
                # "2025-05-09T12:00:00Z"
                start_dt = parser.isoparse(s["start_time"])
                end_dt = parser.isoparse(s["end_time"])
                title = s["title"]
                cat = s['category']['name']
                
                # This will be either America/Chicago etc. or UTC
                start_local = start_dt.astimezone(ZoneInfo(user_tz))
                end_local = end_dt.astimezone(ZoneInfo(user_tz))
                
                start_str = start_local.strftime("%A, %B %d %Y at %I:%M %p %Z")
                end_str = end_local.strftime("%A, %B %d %Y at %I:%M %p %Z")
                date_key = start_local.strftime("%A, %B %d %Y")
                
                stream_info = (
                    f"{streamEmoji} **{title}**\n"
                    f"  <:cocoascontroller:1378540036437573734> Playing: {cat}\n"
                    f"  {boba} From: {start_str} → {end_str}\n"
                )
                
                if date_key not in groups:
                    groups[date_key] = []
                groups[date_key].append(stream_info)

            embed = discord.Embed(
                title=f"🩷 {name}'s Schedule",
                color=discord.Color(value=0xf8e7ef)
            )
            
            for date_key, streams in groups.items():
                day_value = "\n".join(streams)
                embed.add_field(
                    name=f"{personEmoji} {date_key}",
                    value=day_value,
                    inline=False
                )
                
            await interaction.followup.send(embed=embed, ephemeral=False)
        except Exception as e:
            logger.exception(f"Error fetching schedule: {e}")
            await interaction.followup.send(f"❌ Error fetching schedule: {e}", ephemeral=True)
    
async def get_user_timezone(user_id):
    try:
        hit = await fetchrow("""
            SELECT * FROM user_timezone WHERE user_id = $1
        """, user_id)

        return hit["timezone"] if hit is not None else None
    except Exception as e:
        logger.exception(f"Error fetching timezone: {e}")
        return None

async def setup(bot):
    await bot.add_cog(TwitchCog(bot))