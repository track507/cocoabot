import discord.ext
from discord.ext import commands
from discord import app_commands
from helpers.autocomplete import streamer_autocomplete
from dateutil import parser
from zoneinfo import ZoneInfo
from twitchAPI.helper import first
from twitchAPI.type import TwitchResourceNotFound
from twitchAPI.oauth import UserAuthenticator
from helpers.constants import (
    is_whitelisted,
    get_cocoasguild,
    get_twitch
)
from psql import (
    fetchrow
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
            except Exception as e:
                logger.exception(f"Error in get_channel_stream_schedule: {e}")
                await interaction.followup.send(f"❌ Error fetching schedule: {e}", ephemeral=True)
                return
                
            # debug 
            logger.info(f"hit: {hit}")
            # If there's a schedule, iterate over each segment
            segments = hit.segments
            name = hit.broadcaster_name
    
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
                start_dt = s.start_time
                end_dt = s.end_time
                stream_title = s.title or 'Untitled Stream'
                cat = s.category
                recurring = s.is_recurring
                cat_name = cat.name if cat is not None else "No Category"

                recurrence_text = ""
                if recurring:
                    recurrence_text = "(Recurring)"
                
                # This will be either America/Chicago etc. or UTC
                start_local = start_dt.astimezone(ZoneInfo(user_tz))
                end_local = end_dt.astimezone(ZoneInfo(user_tz))
                
                start_str = start_local.strftime("%I:%M %p")
                end_str = end_local.strftime("%I:%M %p")
                date_key = start_local.strftime("%A, %B %d")
                es2 = "\u2003\u2003"
                stream_info = (
                    f"{streamEmoji} **{stream_title}**\n"
                    f"{es2}<:cocoascontroller:1378540036437573734> Playing: {cat_name}\n"
                    f"{es2}{boba} From: {start_str} → {end_str} {recurrence_text}\n"
                )
                
                if date_key not in groups:
                    groups[date_key] = []
                groups[date_key].append(stream_info)

            embed = discord.Embed(
                title=f"🩷 {name}'s Schedule",
                color=discord.Color(value=0xf8e7ef)
            )
            pages = []
            
            for date_key, streams in groups.items():
                day_value = "\n".join(streams)

                embed = discord.Embed(
                    title=f"🩷 {name}'s Schedule (Time shown in {user_tz.replace('_', ' ')})",
                    description=f"{personEmoji} {date_key}",
                    color=discord.Color(value=0xf8e7ef)
                )
                embed.add_field(
                    name="Streams",
                    value=day_value,
                    inline=False
                )
                pages.append(embed)
                
            from handlers.buttons import PaginatorEmbedView
            view = PaginatorEmbedView(interaction, pages)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=False)
        except Exception as e:
            logger.exception(f"Error fetching schedule: {e}")
            await interaction.followup.send(f"❌ Error fetching schedule: {e}", ephemeral=True)
    
    # use twitchAPI oAuth to generate an oAuth link and use a refresh_token to auto refresh
    @app_commands.command(name="authorizetwitch", description="Authorize Twitch with oAuth")
    @is_whitelisted()
    async def oauth_user(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            from helpers.constants import get_twitch_auth_scope, OAUTH_CALLBACK_URL
            twitch = get_twitch()
            
            # Required permission to use /createclip
            target_scope = get_twitch_auth_scope()
            auth = UserAuthenticator(
                twitch,
                target_scope,
                force_verify=False,
                url=f"{OAUTH_CALLBACK_URL}?state={interaction.user.id}"
            )
            # get link to authorize
            auth_url = auth.return_auth_url()
            await interaction.response.send_message(f"Please authorize here: {auth_url}", ephemeral=True)
        except Exception as e:
            logger.exception("Error in /authorizetwitch command")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    # create clips (the last 30 seconds of a 90 second window)
    # https://dev.twitch.tv/docs/api/reference/#create-clip
    @app_commands.command(name="createclip", description="Clip the last 30 seconds of a 90 second window")
    @is_whitelisted()
    async def create_clip(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            from web.webserver import get_user_authentication, refresh_user_token, is_valid_token
            from datetime import datetime
            from helpers.constants import get_twitch_auth_scope
            
            twitch = get_twitch()
            hit = await get_user_authentication(interaction.user.id)
            target_scope = get_twitch_auth_scope()
            
            if not hit:
                await interaction.followup.send("Please run /authorizetwitch first to link your Twitch account.", ephemeral=True)
                return
            
            access_token = hit["access_token"]
            refresh_token = hit["refresh_token"]
            expires_at = hit["expires_at"]
            
            if datetime.now() >= expires_at:
                try:
                    # check if the token is valid
                    is_access_token_valid = await is_valid_token(access_token)
                    if not is_access_token_valid:
                        await interaction.followup.send("Your Twitch token is invalid/revoked, please use /authorizetwitch again.", ephemeral=True)
                        return
                    # now that we know it's a valid access token, try to refresh it
                    refreshed = await refresh_user_token(interaction.user.id, refresh_token, twitch.app_id, twitch.app_secret)
                    if refreshed is None:
                        await interaction.followup.send("Failed to refresh Twitch token. Please run /authorizetwitch again.", ephemeral=True)
                        return
                    access_token = refreshed["access_token"]
                    refresh_token = refreshed["refresh_token"]
                except Exception as e:
                    logger.exception(f"Error in validating/refreshing token in /createclip command: {e}")
                    await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
                    return
                
            twitch.set_user_authentication(access_token, target_scope, refresh_token)
            from twitchAPI.helper import first
            user = await first(twitch.get_users(logins=["cocoakissies"]))
            if not user or not user.id:
                await interaction.followup.send("❌ Twitch user not found.", ephemeral=True)
                return
            
            # this returns a CreatedClip object with id and edit_url
            mention = interaction.user.mention
            try:
                response = await twitch.create_clip(broadcaster_id=user.id)
            except Exception as e:
                await interaction.followup.send(f"Error with creating clip: {e}")
                return
            
            clip_id = response.id
            clip_edit_url = response.edit_url
            clip_url = f"https://clips.twitch.tv/{clip_id}"
            
            # build the response embed
            embed = discord.Embed(
                title=f"{mention} just clipped!",
                description=f"View the clip [here]({clip_url})",
                color=discord.Color(value=0xf8e7ef)
            )
            await interaction.followup.send(embed=embed, ephemeral=False)
            await interaction.followup.send(f"Clipped successfully! You can edit the clip here: {clip_edit_url}", ephemeral=True)

        except Exception as e:
            logger.exception(f"Error in /createclip command: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            
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