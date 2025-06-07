from twitchAPI.helper import first
import discord, asyncio
from psql import (
    fetch, 
    fetchrow, 
    execute, 
    fetchval,
    close_pool
)
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
import helpers.timezones as tz
from helpers.streamersac import streamer_autocomplete
from helpers.helpers import (
    setup,
    handle_stream_offline,
    handle_stream_online
)
from helpers.constants import (
    is_whitelisted,
    DISCORD_TOKEN
)
import helpers.constants as constants
from handlers.birthday import check_birthdays, announce_birthday
from handlers.logger import logger

load_dotenv()

"""
    I know I can use discord webhook in the discord developer portal but at that point it was a sunk cost...
"""

bot = None
cocoasguild = None
privateguild = None
twitch = None
eventsub = None

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# startup
@bot.event
async def on_ready():
    global cocoasguild, privateguild, bot, twitch, eventsub
    await setup(bot)
    
    bot = constants.bot
    cocoasguild = constants.cocoasguild
    privateguild = constants.privateguild
    eventsub = constants.eventsub
    twitch = constants.twitch
    logger.info(f"Logged in as {bot.user}")
    await tree.sync()

# Check every hour since we defined their tz, we want to announce their birthday at 12am in their tz
@tasks.loop(hours=1)
async def birthday_check():
    logger.info("[BirthdayAnnouncer] Checking for birthdays...")
    hits = await check_birthdays()
    if not hits:
        logger.info("[BirthdayAnnouncer] No birthdays found.")
    else:
        logger.info(f"[BirthdayAnnouncer] Found {len(hits)} birthday(s).")
        await announce_birthday(hits)     

# These commands should only be used by admins
@discord.ext.commands.has_guild_permissions(manage_guild=True)
@discord.app_commands.checks.has_permissions(manage_guild=True)
@tree.command(name="setlivenotifications", description="Configure Twitch live notifications.")
@is_whitelisted()
@app_commands.describe(twitch_username="Twitch username", role="Role to ping", channel="Channel to send notifications")
async def setlivenotifications(interaction: discord.Interaction, twitch_username: str, role: discord.Role, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    
    try:
        user = await first(twitch.get_users(logins=[twitch_username]))
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
            await interaction.followup.send("Twitch user not found.", ephemeral=True)
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
            await interaction.followup.send(f"Notifications for {twitch_name} already setup. Use /removenotification {twitch_name} before attempting to use this command again.", ephemeral=True)
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
        
        await eventsub.listen_stream_online(
            broadcaster_user_id=broadcaster_id,
            callback=handle_stream_online
        )
        await eventsub.listen_stream_offline(
            broadcaster_user_id=broadcaster_id,
            callback=handle_stream_offline
        )
        
        await interaction.followup.send(f"Notifications for {twitch_name} setup successfully.", ephemeral=True)
        
    except Exception as e:
        logger.exception("Error in setlivenotifications")
        await interaction.followup.send(f"Error: {e}", ephemeral=True)

@discord.ext.commands.has_guild_permissions(manage_guild=True)
@discord.app_commands.checks.has_permissions(manage_guild=True)
@tree.command(name="removenotification", description="Remove Twitch live notification.")
@is_whitelisted()
@app_commands.describe(twitch_username="Select a Twitch user from this server")
@app_commands.autocomplete(twitch_username=streamer_autocomplete)
async def removenotification(interaction: discord.Interaction, twitch_username: str):
    await interaction.response.defer(ephemeral=True)
    try:
        user = await first(twitch.get_users(logins=[twitch_username]))
        if not user or not user.id:
            await interaction.followup.send("❌ Twitch user not found.", ephemeral=True)
            return

        row = await fetchrow(
            "SELECT 1 FROM notification WHERE broadcaster_id = $1 AND guild_id = $2",
            str(user.id),
            interaction.guild.id
        )
        if not row:
            await interaction.followup.send(f"⚠️ No notification found for {user.display_name}.", ephemeral=True)
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
        await interaction.followup.send(f"✅ Removed notifications for {user.display_name}.", ephemeral=True)

    except Exception as e:
        logger.exception("Error in removenotification")
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@tree.command(name="liststreamers", description="List all streamers with notifications setup in this server.")
@is_whitelisted()
async def liststreamers(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    try:
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
        logger.exception("Error in liststreamers")
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@tree.command(name="status", description="Check Cocoa's Twitch status")
@is_whitelisted()
@app_commands.describe(twitch_username="Select a Twitch user from this server")
@app_commands.autocomplete(twitch_username=streamer_autocomplete)
async def status(interaction: discord.Interaction, twitch_username: str):
    await interaction.response.defer(ephemeral=True)

    try:
        user = await first(twitch.get_users(logins=[twitch_username]))
        if not user:
            await interaction.followup.send("❌ Twitch user not found.", ephemeral=True)
            return

        stream = None
        async for s in twitch.get_streams(user_id=[user.id]):
            stream = s
            break

        streamEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLicense") if cocoasguild else ''
        personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else ''

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
                name=f"<:cocoascontroller:1378540036437573734> Game:",
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
@discord.app_commands.checks.has_permissions(manage_guild=True)
@tree.command(name="setup", description="Setup birthday notifications")
@is_whitelisted()
@app_commands.describe(channel="The channel used for birthdays.", role="The role to ping for those wanting to know when a birthday happens.")
async def birthdaysetup(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
    await interaction.response.defer(ephemeral=True)
    try:
        from handlers.buttons import BirthdaySetupButton
        existing = await fetchrow("""
            SELECT * FROM birthday_guild WHERE guild_id = $1
        """,
            interaction.guild.id
        )
        
        if existing:
            embed = discord.Embed(
                title="Configuration Already Exists",
                description="Setup has already been completed for this server.\nWould you like to overwrite the existing configuration?",
                color=discord.Color.orange()
            )
            view = BirthdaySetupButton(interaction, channel, role)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            return
            
        # If the guild isn't setup
        await execute("""
            INSERT INTO birthday_guild (guild_id, channel_id, role_id)
            VALUES ($1, $2, $3)
        """,
            interaction.guild.id,
            channel.id,
            role.id if role else None
        )
        embed = discord.Embed(
            title="Setup Complete!",
            color=discord.Color(value=0xf8e7ef)
        )
        embed.add_field(
            name="Channel",
            value=f"Birthday message's will appear in {channel.mention}"
        )
        embed.add_field(
            name="Role",
            value=f"No Role Set" if not role else f'Notifying {role.mention} when birthday\'s appears'
        )
        await interaction.followup.send(embed=embed, ephemeral=False)
    except Exception as e:
        logger.exception("Error in /setup command")
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@tree.command(name="set", description="Set your birthday (Once set, can't update for 3 months!)")
@is_whitelisted()
@app_commands.describe(birthdate="Month and day you're born.", time_zone="Timezone you live in")
@app_commands.autocomplete(time_zone=tz.timezone_autocomplete)
async def setbirthday(interaction: discord.Interaction, birthdate: str, time_zone: str):
    await interaction.response.defer(ephemeral=True)
    try:
        from helpers.birthdayparser import parse
        try:
            birthdate = parse(birthdate)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        
        config = await fetchrow("""
            SELECT * FROM birthday_guild WHERE guild_id = $1
        """,
            interaction.guild.id
        )
        if config is None:
            await interaction.followup.send("Cannot find server configuration.\nPlease have someone with manage guild permissions to use the /set command", ephemeral=True)
            return
        
        existing = await fetchrow("""
            SELECT * FROM birthday_user WHERE guild_id = $1 AND user_id = $2
        """,
            interaction.guild.id,
            interaction.user.id
        )
        if existing:
            from datetime import datetime, timedelta
            last_updated = existing['last_updated']
            can_update = last_updated < datetime.now() - timedelta(days=90)
            
            embed = discord.Embed(
                title="Birthday Found",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="Current Birthday",
                value=f"Date: {existing['birthdate']}\nTimezone: {existing['timezone']}",
                inline=False
            )
            embed.add_field(
                name="Last Updated",
                value=f"{last_updated.strftime('%Y-%m-%d %H:%M:%S')}",
                inline=False
            )
            
            if can_update:
                from handlers.buttons import BirthdayUpdateButton
                view = BirthdayUpdateButton(interaction, birthdate, time_zone)
                embed.add_field(
                    name="New Birthday You Are Setting",
                    value=f"Date: {birthdate}\nTimezone: {time_zone}",
                    inline=False
                )
                await interaction.followup.send(
                    content="It's been over 3 months! You may update your birthday.",
                    embed=embed,
                    view=view,
                    ephemeral=True
                )
                return
            else:
                embed = discord.Embed(
                    title="Birthday Found",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="Current Birthday",
                    value=f"Date: {existing['birthdate']}\nTimezone: {existing['timezone']}",
                    inline=False
                )
                embed.add_field(
                    name="Last Updated",
                    value=f"{last_updated.strftime('%Y-%m-%d %H:%M:%S')}",
                    inline=False
                )
                await interaction.followup.send(
                    content="It has not been 3 months. You cannot update your birthday yet.",
                    embed=embed,
                    ephemeral=True
                )
                return
        
        await execute("""
            INSERT INTO birthday_user (guild_id, user_id, birthdate, timezone)
            VALUES ($1, $2, $3, $4)
        """,
            interaction.guild.id,
            interaction.user.id,
            birthdate,
            time_zone
        )
        
        embed = discord.Embed(
            title="Birthday has been set!",
            color=discord.Color(value=0xf8e7ef)
        )
        embed.add_field(
            name="Birthday",
            value=f"Date: {birthdate}\nTimezone: {time_zone}",
            inline=False
        )
        
        channel = interaction.guild.get_channel(config['channel_id'])
        channel_mention = channel.mention if channel else f"<#{config['channel_id']}>"
        embed.add_field(
            name="Server Config",
            value=f"Your birthday will be mentioned in {channel_mention}",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
            
    except Exception as e:
        logger.exception("Error in /set command")
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@discord.ext.commands.has_guild_permissions(moderate_members=True)
@discord.app_commands.checks.has_permissions(moderate_members=True)
@tree.command(name="remove", description="Delete a user's birthday, effectively allowing them to use /set again.")
@is_whitelisted()
@app_commands.describe(user="The user to remove the birthday from.")
async def removebirthday(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    try:
        existing = await fetchrow("""
            SELECT * FROM birthday_user WHERE guild_id = $1 AND user_id = $2
        """,
            interaction.guild.id,
            user.id
        )
        
        if not existing:
            await interaction.followup.send("User was not found in the existing database. If it's their first time, use /set.", ephemeral=True)
            return
        
        await execute("""
            DELETE FROM birthday_user WHERE guild_id = $1 and user_id = $2
        """,
            interaction.guild.id,
            user.id
        )
        
        await interaction.followup.send(f"{user.mention};'s birthday has been successfully removed.", ephemeral=True)
            
    except Exception as e:
        logger.exception("Error in /remove command")
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        
# About
@tree.command(name="about", description="About the bot.")
@is_whitelisted()
async def about(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        streamEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLicense") if cocoasguild else ''
        personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else ''
        shyEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaShy") if cocoasguild else ''
        bonk = discord.utils.get(cocoasguild.emojis, name="cocoaBonk") if cocoasguild else ''
        mwah = discord.utils.get(cocoasguild.emojis, name="cocoaMwah") if cocoasguild else ''
        
        embed = discord.Embed(
            title=f"{streamEmoji} About Cocoabot",
            url="https://github.com/track507/cocoabot",
            description=(
                "Cocoabot is built for **Cocoa** (A.K.A *cocoakissies*)."
                "\nIts primary function is to notify users when Cocoa goes live"
                "\nAdditional features include (as of 6-7-2025):"
                "\n\u2022 Tracking birthdays by sending out notification in specified channels"
            ),
            color=discord.Color(value=0xf8e7ef)
        )
        embed.add_field(
            name=f"{personEmoji} Creator",
            value=(
                "**Developed and maintained by** TrackAtNite ([track507 on GitHub](https://github.com/track507/cocoabot)).\n"
                "This bot is actively improved as new features are needed or requested."
            ),
            inline=False
        )
        embed.add_field(
            name=f"{shyEmoji} Bugs",
            value=(
                "If you encounter any bugs, please either create an issue with the `bug` label on "
                "[GitHub](https://github.com/track507/cocoabot/issues) or use the `/bug` command *(coming soon)*."
            ),
            inline=False
        )
        embed.add_field(
            name="<:cocoascontroller:1378540036437573734> Features & Suggestions",
            value=(
                "Have ideas for new features? Open an issue with the `enhancement` label on "
                "[GitHub](https://github.com/track507/cocoabot/issues) or use the `/feature` command *(coming soon)*."
            ),
            inline=False
        )
        embed.add_field(
            name=f"{bonk} Privacy",
            value=(
                "**Please respect my privacy.**\n"
                "\u2022 Do not contact me directly - unwanted messages will be ignored and may result in a block.\n"
                "\u2022 Cocoa does not manage this bot, so please **do not contact Cocoa** or her moderators about bot issues.\n\n"
                "**User privacy:**\n"
                "\u2022 This bot only stores the **minimum required data** to function properly.\n"
                "\u2022 No personal data is saved beyond what is strictly necessary."
            ),
            inline=False
        )
        embed.add_field(
            name=f"{mwah} Misc.",
            value=(
                "\u2022 This bot is **open source** for transparency and learning.\n"
                "\u2022 I believe in sharing and open sourcing projects to help and inspire others."
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        logger.exception("About failed")
        await interaction.followup.send(f"❌ About failed: `{str(e)}`", ephemeral=True)
        
# Admin debugs.
@discord.ext.commands.has_guild_permissions(manage_guild=True)
@discord.app_commands.checks.has_permissions(manage_guild=True)
@tree.command(name="testtwitch", description="Test Twitch API and EventSub integration.")
@is_whitelisted()
async def testtwitch(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        user = await first(twitch.get_users(logins=["lxchet"]))
        if not user:
            await interaction.followup.send("❌ Twitch API: User not found.", ephemeral=True)
            return

        broadcaster_id = user.id
        twitch_login = user.login
        twitch_name = user.display_name
        twitch_link = f"https://twitch.tv/{twitch_login}"
        twitch_thumbnail = user.profile_image_url
        msg = f"✅ Twitch API: Found user `{twitch_name}` (ID: {broadcaster_id}) Twitch link: <{twitch_link}>\n"

        # Check if in DB already
        existing = await fetchrow("SELECT * FROM notification WHERE broadcaster_id = $1", broadcaster_id)
        already_exists = existing is not None

        # Remove all existing subs for this user
        subs = await twitch.get_eventsub_subscriptions()
        for sub in subs.data:
            if sub.type in ('stream.online', 'stream.offline') and sub.condition.get('broadcaster_user_id') == broadcaster_id:
                await twitch.delete_eventsub_subscription(sub.id)
                msg += f"⚠️ Removed existing subscription ID: {sub.id}\n"

        # Add new test subscription
        await eventsub.listen_stream_online(
            broadcaster_user_id=broadcaster_id,
            callback=handle_stream_online
        )
        await eventsub.listen_stream_offline(
            broadcaster_user_id=broadcaster_id,
            callback=handle_stream_offline
        )
        
        msg += "✅ Created new EventSub subscription.\n"

        # Confirm and clean up all matching subs
        new_subs = await twitch.get_eventsub_subscriptions()
        matching_subs = [
            sub for sub in new_subs.data
            if sub.type in ('stream.online', 'stream.offline') and sub.condition.get('broadcaster_user_id') == broadcaster_id
        ]
        if matching_subs:
            for sub in matching_subs:
                await twitch.delete_eventsub_subscription(sub.id)
                msg += f"🧹 Deleted subscription ID for {sub.type}: {sub.id}\n"
        else:
            msg += "❌ Failed to verify the new subscription.\n"

        # Reinsert original notification (if existed)
        if already_exists:
            await eventsub.listen_stream_online(
                broadcaster_user_id=broadcaster_id,
                callback=handle_stream_online
            )
            await eventsub.listen_stream_offline(
                broadcaster_user_id=broadcaster_id,
                callback=handle_stream_offline
            )
            msg += f"🔄 Restored original subscription.\n"
        
        # Load emoji from server, or fallback
        streamEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLicense") if cocoasguild else ""

        emoji_embed = discord.Embed(
            title=f"🩷 {user.display_name} is OFFLINE",
            description=f"{streamEmoji or 'BOT_NOT_IN_SERVER'} Title: Test stream title",
            url=f"https://twitch.tv/{user.login}",
            color=discord.Color.greyple()
        )

        emoji_embed.add_field(
            name="<:cocoascontroller:1378540036437573734> Game Emoji",
            value="Test passed",
            inline=True
        )

        emoji_embed.add_field(
            name="Watch Now",
            value=f"https://twitch.tv/{user.login}",
            inline=True
        )

        emoji_embed.set_thumbnail(url=twitch_thumbnail)

        await interaction.followup.send(
            content=msg,
            embed=emoji_embed,
            ephemeral=True
        )

    except Exception as e:
        logger.exception("Twitch test failed")
        await interaction.followup.send(f"❌ Twitch test failed: `{str(e)}`", ephemeral=True)

@discord.ext.commands.has_guild_permissions(manage_guild=True)
@discord.app_commands.checks.has_permissions(manage_guild=True)
@tree.command(name="testbirthday", description="Test birthday integration.")
@is_whitelisted()
async def testbirthday(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        from datetime import datetime
        server_config = await fetchrow("""
            SELECT * FROM birthday_guild WHERE guild_id = $1                   
        """,
            interaction.guild.id,
        )
        if server_config is None:
            interaction.followup.send(f"Could not find configuration for this server.\nPlease use /setup before using this command.")
            return
        test_user = await fetchrow("""
            SELECT * FROM birthday_user WHERE guild_id = $1 AND user_id = $2
        """,
            interaction.guild.id,
            bot.user.id
        )
        if test_user is None:
            birthdate = "01-01"
            time_zone = "UTC"
            embed = discord.Embed(
                title="Birthday has been set!",
                color=discord.Color(value=0xf8e7ef)
            )
            embed.add_field(
                name="Birthday",
                value=f"Date: {birthdate}\nTimezone: {time_zone}",
                inline=False
            )
            guild_setup = await fetchrow("""
                SELECT * FROM birthday_guild WHERE guild_id = $1
            """,
                interaction.guild.id
            )
            channel = interaction.guild.get_channel(guild_setup['channel_id'])
            channel_mention = channel.mention if channel else f"<#{guild_setup['channel_id']}>"
            embed.add_field(
                name="Server Config",
                value=f"Your birthday will be mentioned in {channel_mention}",
                inline=False
            )
            await execute("""
                INSERT INTO birthday_user (guild_id, user_id, birthdate, timezone)
                VALUES ($1, $2, $3, $4)
            """,
                interaction.guild.id,
                bot.user.id,
                birthdate,
                time_zone,
            )
            await interaction.followup.send(
                content="Adding bot as a Test User.",
                embed=embed
            )
            
        hit = await fetchrow("""
            SELECT * FROM birthday_user WHERE guild_id = $1 AND user_id = $2
        """,
            interaction.guild.id,
            bot.user.id
        )
        # build embed to send a ephermeral message
        guild = bot.get_guild(hit['guild_id'])
        member = guild.get_member(hit['user_id'])
        role_mention = ""
        if server_config['role_id']:
            role = guild.get_role(server_config['role_id'])
            if role:
                role_mention = role.mention
        
        personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else ""
        
        embed = discord.Embed(
            title=f"{personEmoji} Today is the following user(s) birthdays!",
            color=discord.Color.gold()
        )
        line = f"{member.mention}"
        embed.add_field(
            name="\u200b",
            value=line,
            inline=False
        )
        embed.set_footer(text="Happy Birthday!!!")
        embed.timestamp = datetime.now()
        await interaction.followup.send(content=role_mention if role_mention else None, embed=embed, ephemeral=True)
        
        if test_user is None:
            msg = "Destroying Test User Birthday..."
            await execute("""
                DELETE FROM birthday_user WHERE guild_id = $1 AND user_id = $2
            """,
                interaction.guild.id,
                bot.user.id
            )
            msg += "\nTest User successfully removed"
            await interaction.followup.send(msg, ephemeral=True)
        
    except Exception as e:
        logger.exception("Birthday test failed")
        await interaction.followup.send(f"❌ Birthday test failed: `{str(e)}`", ephemeral=True)

async def main():
    try:
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Received SIGINT or KeyboardInterrupt, shutting down...")
    except Exception as e:
        logger.exception("Error starting bot")
    finally:
        await close_pool()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())