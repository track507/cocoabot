import discord.ext
from discord.ext import commands
from discord import app_commands
from helpers.autocomplete import (
    streamer_autocomplete, 
    video_types_autocomplete, 
    features_autocomplete
)
from dateutil import parser
from zoneinfo import ZoneInfo
from twitchAPI.helper import first
from twitchAPI.type import TwitchResourceNotFound, VideoType
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
    async def schedule(self, interaction: discord.Interaction):
        await interaction.response.defer() 
        try:
            # get user if any
            twitch = get_twitch()
            user = await first(twitch.get_users(logins=["cocoakissiess"]))
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
                logger.exception(f"Error in /get_channel_stream_schedule: {e}")
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
            controllerEmoji = discord.utils.get(self.bot.emojis, name="cocoascontroller") or '🎮'
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
                    f"{es2}{controllerEmoji} Playing: {cat_name}\n"
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
            
    @app_commands.command(name="status", description="Check Cocoa's Twitch status")
    @is_whitelisted()
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            twitch = get_twitch()
            cocoasguild = get_cocoasguild()
            user = await first(twitch.get_users(logins=["cocoakissiess"]))
            if not user:
                await interaction.followup.send("❌ Twitch user not found.", ephemeral=True)
                return

            stream = None
            async for s in twitch.get_streams(user_id=[user.id]):
                stream = s
                break

            cocoasguild = get_cocoasguild()
            streamEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLicense") if cocoasguild else '🎬'
            personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else '🩷'
            controllerEmoji = discord.utils.get(self.bot.emojis, name="cocoascontroller") or '🎮'

            if stream:
                embed = discord.Embed(
                    title=f"🩷 {stream.user_name} is LIVE",
                    url=f"https://twitch.tv/{user.login}",
                    color=discord.Color(value=0xf8e7ef)
                )
                embed.add_field(
                    name=f"{streamEmoji} Title:",
                    value=stream.title or "No stream title found",
                    inline=False
                )
                embed.add_field(
                    name=f"{controllerEmoji} Game:",
                    value=stream.game_name or "Unknown",
                    inline=False
                )
                embed.add_field(
                    name=f"{personEmoji} Watch Now:",
                    value=f"https://twitch.tv/{user.login}",
                    inline=False
                )
                embed.set_thumbnail(url=stream.thumbnail_url.replace("{width}", "320").replace("{height}", "180"))

            else:
                embed = discord.Embed(
                    title=f"🩷 {user.display_name} is OFFLINE",
                    url=f"https://twitch.tv/{user.login}",
                    color=discord.Color.greyple()
                )

            await interaction.followup.send(embed=embed, ephemeral=False)

        except Exception as e:
            logger.exception("Error in /status command")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            
    @discord.ext.commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="removenotification", description="Remove Twitch live notification.")
    @is_whitelisted()
    async def removenotification(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            from psql import execute
            twitch = get_twitch()
            user = await first(twitch.get_users(logins=["cocoakissiess"]))
            if not user or not user.id:
                await interaction.followup.send("❌ Twitch user not found.", ephemeral=True)
                return

            row = await fetchrow(
                "SELECT 1 FROM notification WHERE broadcaster_id = $1 AND guild_id = $2",
                str(user.id),
                interaction.guild.id
            )
            if not row:
                await interaction.followup.send(f"⚠️ No notification found for {user.display_name}.", ephemeral=False)
                return

            await execute(
                "DELETE FROM notification WHERE broadcaster_id = $1 AND guild_id = $2",
                str(user.id),
                interaction.guild.id
            )
            subs = await twitch.get_eventsub_subscriptions()
            for sub in subs.data:
                if sub.type in ('stream.online', 'stream.offline') and sub.condition.get('broadcaster_user_id') == user.id:
                    await twitch.delete_eventsub_subscription(sub.id)
            await interaction.followup.send(f"✅ Removed notifications for {user.display_name}.", ephemeral=False)

        except Exception as e:
            logger.exception("Error in /removenotification")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            
    @discord.ext.commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="setlivenotifications", description="Configure Twitch live notifications.")
    @is_whitelisted()
    @app_commands.describe(twitch_username="Twitch username", role="Role to ping", channel="Channel to send notifications")
    async def setlivenotifications(self, interaction: discord.Interaction, twitch_username: str, role: discord.Role, channel: discord.TextChannel):
        await interaction.response.defer()
        
        try:
            from helpers.constants import get_eventsub
            from helpers.helpers import handle_stream_offline, handle_stream_online
            from psql import execute
            user = await first(get_twitch().get_users(logins=[twitch_username]))
            """
            Example response:
            TwitchUser(
                id=113142538, 
                login=lxchet, 
                display_name=Lxchet, 
                type=, 
                broadcaster_type=, 
                description=Siege and Val all the wayDoing this for fun, 
                profile_image_url=https://static-cdn.jtvnw.net/jtv_user_pictures/95500c7f-0536-4361-98cf-ead573d97315-profile_image-300x300.png, 
                offline_image_url=, 
                view_count=0, 
                email=None, 
                created_at=2016-01-18 05:42:39+00:00)
            """
            # print(user)
            if not user.id or not user.login:
                await interaction.followup.send("Twitch user not found.", ephemeral=False)
                return

            broadcaster_id = user.id
            twitch_login = user.login
            twitch_name = user.display_name
            twitch_link = f"https://twitch.tv/{twitch_login}"
            
            # print debug
            logger.debug(f"broadcaster_id: {broadcaster_id}, twitch_login: {twitch_login}, twitch_name: {twitch_name}, twitch_link: {twitch_link}")
            
            # check if broadcaster_id already exists
            existing = await fetchrow(
                "SELECT * FROM notification WHERE broadcaster_id = $1 AND guild_id = $2",
                broadcaster_id,
                interaction.guild.id
            )
            if existing:
                await interaction.followup.send(f"Notifications for {twitch_name} already setup. Use /removenotification {twitch_name} before attempting to use this command again.", ephemeral=False)
                return
            
            # store in database
            await execute("""
                INSERT INTO notification (broadcaster_id, twitch_name, twitch_link, role_id, channel_id, guild_id)
                VALUES ($1, $2, $3, $4, $5, $6)
            """,
                str(broadcaster_id),
                twitch_name,
                twitch_link,
                role.id,
                channel.id,
                interaction.guild.id,
            )
            
            await get_eventsub().listen_stream_online(
                broadcaster_user_id=broadcaster_id,
                callback=handle_stream_online
            )
            await get_eventsub().listen_stream_offline(
                broadcaster_user_id=broadcaster_id,
                callback=handle_stream_offline
            )
            
            await interaction.followup.send(f"Notifications for {twitch_name} setup successfully.", ephemeral=False)
            
        except Exception as e:
            logger.exception("Error in /setlivenotifications")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)
            
    @app_commands.command(name="liststreamers", description="List all streamers with notifications setup in this server.")
    @is_whitelisted()
    async def liststreamers(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            from psql import fetch
            rows = await fetch(
                "SELECT twitch_name, twitch_link FROM notification WHERE guild_id = $1",
                interaction.guild.id
            )
            if not rows:
                await interaction.followup.send("There are no streamers with notifications set up in this server.", ephemeral=False)
                return
            
            msg = "**📺 Streamers with notifications enabled in this server:**\n"
            for row in rows:
                msg += f"- `{row['twitch_name']}` — <{row['twitch_link']}>\n"

            await interaction.followup.send(msg, ephemeral=False)
        
        except Exception as e:
            logger.exception("Error in /liststreamers")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    @discord.ext.commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.command(name="alert", description="Manually alert users when a streamer goes live")
    @is_whitelisted()
    async def alert(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            from helpers.constants import get_twitch, get_cocoasguild
            from psql import fetchrow, execute
            twitch = get_twitch()
            cocoasguild = get_cocoasguild()
            user = await first(twitch.get_users(logins=["cocoakissiess"]))
            if not user:
                await interaction.followup.send("❌ Twitch user not found.", ephemeral=True)
                return

            stream = None
            async for s in twitch.get_streams(user_id=[user.id]):
                stream = s
                break
            if stream:
                # Build stream info
                broadcaster_id = user.id
                guild_id = interaction.guild.id
                title = stream.title.strip() if stream.title else "No stream title found"
                row = await fetchrow(
                    "SELECT channel_id, role_id FROM notification WHERE broadcaster_id = $1 AND guild_id = $2",
                    broadcaster_id,
                    guild_id
                )
                
                if not row:
                    await interaction.followup.send("No notification configuration can be found for this server", ephemeral=True)
                    return 
                
                # Set to false so the next stream.online event can register correctly.
                await execute(
                    "UPDATE notification SET is_live = FALSE WHERE broadcaster_id = $1 AND guild_id = $2",
                    broadcaster_id,
                    guild_id
                )
                
                # Prepare embed
                cocoasguild = get_cocoasguild()
                streamEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLicense") if cocoasguild else '🎬'
                personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else '🩷'
                controllerEmoji = discord.utils.get(self.bot.emojis, name="cocoascontroller") or '🎮'

                embed = discord.Embed(
                    title=f"🩷 {user.display_name} is LIVE",
                    url=f"https://twitch.tv/{user.login}",
                    color=discord.Color(value=0xf8e7ef)
                )
                embed.add_field(
                    name=f"{streamEmoji or ''} Title:",
                    value=title,
                    inline=False
                )
                embed.add_field(
                    name=f"{controllerEmoji} Game:",
                    value=stream.game_name or "Unknown",
                    inline=False
                )
                embed.add_field(
                    name=f"{personEmoji or ''} Watch Now:",
                    value=f"https://twitch.tv/{user.login}",
                    inline=False
                )
                embed.set_footer(text="Stream started just now!")
                embed.timestamp = stream.started_at
                embed.set_thumbnail(
                    url=stream.thumbnail_url.replace("{width}", "320").replace("{height}", "180")
                )
                
                channel_id = int(row["channel_id"])
                role_id = int(row["role_id"])
                
                # Get channel in the current guild
                channel = interaction.guild.get_channel(channel_id)
                if not channel:
                    await interaction.followup.send("Channel could not be found.", ephemeral=True)
                    return

                await channel.send(
                    content=f"<@&{role_id}> https://twitch.tv/{user.login}",
                    embed=embed
                )
                await interaction.followup.send("Alert sent to this server.", ephemeral=True)
                return
                
            await interaction.followup.send(f"{user.display_name} is not currently live.")
        except Exception as e:
            logger.exception("Error in /alert")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            
    @app_commands.command(name="clips", description="Get cocoakissiess latest clips!")
    @is_whitelisted()
    @app_commands.describe(features="Featured clips (optional, default NONE): True, False, or None")
    @app_commands.autocomplete(features=features_autocomplete)
    async def clips(self, interaction: discord.Interaction, features: str = "none"):
        await interaction.response.defer()
        
        try:
            twitch = get_twitch()
            user = await first(twitch.get_users(logins=["cocoakissiess"]))
            if not user.id or not user.login:
                await interaction.followup.send("Twitch user not found.", ephemeral=True)
                return
            
            features_type_map = {
                "none" : None,
                "true": True,
                "false": False
            }
            
            if features.lower() not in features_type_map:
                await interaction.followup.send(f"❌ Invalid features type: `{features}`. Please use the autocomplete suggestions.", ephemeral=True)
                return
            
            feature_type = features_type_map.get(features.lower(), None)
            
            clips = [clip async for clip in twitch.get_clips(broadcaster_id=user.id, first=25, is_featured=feature_type)]
            
            # Set display type
            if features.lower() == "none":
                type_display = "All"
            elif features.lower() == "true":
                type_display = "Featured"
            else:
                type_display = "Non-Featured"
            
            if not clips:
                await interaction.followup.send(f"No clips found for {user.display_name} with features type {type_display}.", ephemeral=False)
                return
            
            cocoasguild = get_cocoasguild()
            streamEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLicense") if cocoasguild else '🎬'
            bobaEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaBoba") if cocoasguild else '🧋'
            personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else '🩷'
            sparkles = discord.utils.get(cocoasguild.emojis, name="sparkles") if cocoasguild else '✨'
            caught = discord.utils.get(cocoasguild.emojis, name="cocoaCaughtIn4K") if cocoasguild else '👀'
            cokeEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLargeCoke") if cocoasguild else '🥤'
            controllerEmoji = discord.utils.get(self.bot.emojis, name="cocoascontroller") or '🎮'
            
            pages = []
            for clip in clips:
                embed = discord.Embed(
                    title=f"🩷 {clip.broadcaster_name}'s Clips",
                    description=f"Showing {type_display} clips",
                    url=clip.url,
                    color=discord.Color(value=0xf8e7ef)
                )
                
                embed.add_field(name=f"{streamEmoji} Title", value=clip.title or "No title", inline=False)
                
                try:
                    game = await first(twitch.get_games(game_ids=[clip.game_id])) if clip.game_id else None
                except:
                    game = None
                
                embed.add_field(name=f"{controllerEmoji} Game", value=game.name if game else "Unknown", inline=False)
                
                embed.add_field(name=f"{bobaEmoji} Views", value=f"{clip.view_count:,}" if clip.view_count else "0", inline=True)
                
                embed.add_field(name=f"{caught} Date", value=f"<t:{int(clip.created_at.timestamp())}:D>", inline=True)
                
                embed.add_field(name=f"{cokeEmoji} Clipped by", value=f"{clip.creator_name}", inline=True)
                
                # FIX: Use string instead of variable in braces
                embed.add_field(name=f"{sparkles} Type", value="Featured" if clip.is_featured else "Regular", inline=True)
                
                embed.add_field(name=f"{personEmoji} Watch", value=f"{clip.url}", inline=False)
                
                embed.set_thumbnail(url=clip.thumbnail_url if clip.thumbnail_url else "https://i.imgur.com/ktvDsVQ.png")
                
                embed.set_footer(text=f"Clip ID: {clip.id}")
                
                pages.append(embed)
                
            from handlers.buttons import PaginatorEmbedView
            view = PaginatorEmbedView(interaction, pages)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=False)
        except Exception as e:
            logger.exception("Error in /clips")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
                
    @app_commands.command(name="videos", description="Get cocoakissiess latest video's!")
    @is_whitelisted()
    @app_commands.describe(type="Video type (optional, default ALL): archive (VOD's), highlight, upload")
    @app_commands.autocomplete(type=video_types_autocomplete)
    async def videos(self, interaction: discord.Interaction, type: str = "all"):
        await interaction.response.defer()
        
        try:
            twitch = get_twitch()
            user = await first(twitch.get_users(logins=["cocoakissiess"]))
            
            if not user.id or not user.login:
                await interaction.followup.send("Twitch user not found.", ephemeral=True)
                return
            
            # Convert string to VideoType enum
            video_type_map = {
                "all": VideoType.ALL,
                "archive": VideoType.ARCHIVE,
                "highlight": VideoType.HIGHLIGHT,
                "upload": VideoType.UPLOAD
            }
            
            if type.lower() not in video_type_map:
                await interaction.followup.send(f"❌ Invalid video type: `{type}`. Please use the autocomplete suggestions.", ephemeral=True)
                return
            
            video_type = video_type_map.get(type.lower(), VideoType.ALL)
            
            # Get videos
            videos = [video async for video in twitch.get_videos(user_id=user.id, first=25, video_type=video_type)]
            
            if not videos:
                await interaction.followup.send(f"No videos found for {user.display_name} of type {type}.", ephemeral=False)
                return
            
            # Store emojis for use
            cocoasguild = get_cocoasguild()
            streamEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLicense") if cocoasguild else '🎬'
            bobaEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaBoba") if cocoasguild else '🧋'
            personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else '🩷'
            sparkles = discord.utils.get(cocoasguild.emojis, name="sparkles") if cocoasguild else '✨'
            caught = discord.utils.get(cocoasguild.emojis, name="cocoaCaughtIn4K") if cocoasguild else '👀'
            controllerEmoji = discord.utils.get(self.bot.emojis, name="cocoascontroller") or '🎮'

            # Create embeds for each video
            pages = []
            for video in videos:
                embed = discord.Embed(
                    title=f"🩷 {user.display_name}'s Videos",
                    description=f"Showing {type}",
                    url=video.url,
                    color=discord.Color(value=0xf8e7ef)
                )
                
                # Video title and description
                embed.add_field(name=f"{streamEmoji} Title", value=video.title or "No title", inline=False)
                
                if video.description:
                    # Truncate description if too long for embed
                    desc = video.description[:1000] + "..." if len(video.description) > 1000 else video.description
                    embed.add_field(name=f"{controllerEmoji} Description", value=desc, inline=False)
                
                # Video stats
                embed.add_field(name=f"{bobaEmoji} Views", value=f"{video.view_count:,}" if video.view_count else "0", inline=True)
                
                if video.published_at:
                    embed.add_field(name=f"{caught} Date", value=f"<t:{int(video.published_at.timestamp())}:D>", inline=True)
                
                # Video type
                embed.add_field(name=f"{sparkles} Type", value=video.type.value if video.type else "Unknown", inline=True)
                
                # URL
                embed.add_field(name=f"{personEmoji} Watch", value=f"{video.url}", inline=False)
                
                embed.set_thumbnail(url=video.thumbnail_url if video.thumbnail_url else "https://i.imgur.com/ktvDsVQ.png")
                
                # Footer with video ID
                embed.set_footer(text=f"Video ID: {video.id}")
                
                pages.append(embed)
            
            from handlers.buttons import PaginatorEmbedView
            view = PaginatorEmbedView(interaction, pages)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=False)
                
        except Exception as e:
            logger.exception("Error in /videos")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            
    # # use twitchAPI oAuth to generate an oAuth link and use a refresh_token to auto refresh
    # @app_commands.command(name="authorizetwitch", description="Authorize Twitch with oAuth")
    # @is_whitelisted()
    # async def oauth_user(self, interaction: discord.Interaction):
    #     await interaction.response.defer()
    #     try:
    #         from helpers.constants import get_twitch_auth_scope, OAUTH_CALLBACK_URL
    #         twitch = get_twitch()
            
    #         # Required permission to use /createclip
    #         target_scope = get_twitch_auth_scope()
    #         auth = UserAuthenticator(
    #             twitch,
    #             target_scope,
    #             force_verify=False,
    #             url=f"{OAUTH_CALLBACK_URL}?state={interaction.user.id}"
    #         )
    #         # get link to authorize
    #         auth_url = auth.return_auth_url()
    #         await interaction.response.send_message(f"Please authorize here: {auth_url}", ephemeral=True)
    #     except Exception as e:
    #         logger.exception("Error in /authorizetwitch command")
    #         await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    # # create clips (the last 30 seconds of a 90 second window)
    # # https://dev.twitch.tv/docs/api/reference/#create-clip
    # @app_commands.command(name="createclip", description="Clip the last 30 seconds of a 90 second window")
    # @is_whitelisted()
    # async def create_clip(self, interaction: discord.Interaction):
    #     await interaction.response.defer()
    #     try:
    #         from web.webserver import get_user_authentication, refresh_user_token, is_valid_token
    #         from datetime import datetime
    #         from helpers.constants import get_twitch_auth_scope
            
    #         twitch = get_twitch()
    #         hit = await get_user_authentication(interaction.user.id)
    #         target_scope = get_twitch_auth_scope()
            
    #         if not hit:
    #             await interaction.followup.send("Please run /authorizetwitch first to link your Twitch account.", ephemeral=True)
    #             return
            
    #         access_token = hit["access_token"]
    #         refresh_token = hit["refresh_token"]
    #         expires_at = hit["expires_at"]
            
    #         if datetime.now() >= expires_at:
    #             try:
    #                 # check if the token is valid
    #                 is_access_token_valid = await is_valid_token(access_token)
    #                 if not is_access_token_valid:
    #                     await interaction.followup.send("Your Twitch token is invalid/revoked, please use /authorizetwitch again.", ephemeral=True)
    #                     return
    #                 # now that we know it's a valid access token, try to refresh it
    #                 refreshed = await refresh_user_token(interaction.user.id, refresh_token, twitch.app_id, twitch.app_secret)
    #                 if refreshed is None:
    #                     await interaction.followup.send("Failed to refresh Twitch token. Please run /authorizetwitch again.", ephemeral=True)
    #                     return
    #                 access_token = refreshed["access_token"]
    #                 refresh_token = refreshed["refresh_token"]
    #             except Exception as e:
    #                 logger.exception(f"Error in validating/refreshing token in /createclip command: {e}")
    #                 await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    #                 return
                
    #         twitch.set_user_authentication(access_token, target_scope, refresh_token)
    #         from twitchAPI.helper import first
    #         user = await first(twitch.get_users(logins=["cocoakissies"]))
    #         if not user or not user.id:
    #             await interaction.followup.send("❌ Twitch user not found.", ephemeral=True)
    #             return
            
    #         # this returns a CreatedClip object with id and edit_url
    #         mention = interaction.user.mention
    #         try:
    #             response = await twitch.create_clip(broadcaster_id=user.id)
    #         except Exception as e:
    #             await interaction.followup.send(f"Error with creating clip: {e}")
    #             return
            
    #         clip_id = response.id
    #         clip_edit_url = response.edit_url
    #         clip_url = f"https://clips.twitch.tv/{clip_id}"
            
    #         # build the response embed
    #         embed = discord.Embed(
    #             title=f"{mention} just clipped!",
    #             description=f"View the clip [here]({clip_url})",
    #             color=discord.Color(value=0xf8e7ef)
    #         )
    #         await interaction.followup.send(embed=embed, ephemeral=False)
    #         await interaction.followup.send(f"Clipped successfully! You can edit the clip here: {clip_edit_url}", ephemeral=True)

    #     except Exception as e:
    #         logger.exception(f"Error in /createclip command: {e}")
    #         await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            
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