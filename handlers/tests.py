from discord.ext import commands
from discord import app_commands
import discord.ext
from twitchAPI.helper import first
from helpers.constants import (
    is_whitelisted,
    get_cocoasguild,
    get_twitch,
    get_eventsub,
    get_bot
)
from helpers.helpers import (
    handle_stream_offline,
    handle_stream_online
)
from psql import (
    fetchrow, 
    execute
)
from handlers.logger import logger

class TestsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    # Admin debugs.
    @discord.ext.commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="testtwitch", description="Test Twitch API and EventSub integration.")
    @is_whitelisted()
    async def testtwitch(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            twitch = get_twitch()
            eventsub = get_eventsub()
            cocoasguild = get_cocoasguild()
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
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="testbirthday", description="Test birthday integration.")
    @is_whitelisted()
    async def testbirthday(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            bot = get_bot()
            cocoasguild = get_cocoasguild()
            from datetime import datetime
            server_config = await fetchrow("""
                SELECT * FROM birthday_guild WHERE guild_id = $1                   
            """,
                interaction.guild.id,
            )
            if server_config is None:
                await interaction.followup.send(f"Could not find configuration for this server.\nPlease use /setup before using this command.")
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
            line = f"{member.mention} \u2022 {hit['birthdate']}"
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

async def setup(bot):
    await bot.add_cog(TestsCog(bot))