from discord.ext import commands
from discord import (
    HTTPException, 
    app_commands, 
    Interaction, 
    Embed, 
    utils, 
    Color, 
    NotFound, 
    Forbidden,
    Member
)
from handlers.logger import logger
from helpers.constants import (
    is_whitelisted,
    get_cocoasguild
)
from helpers.autocomplete import timezone_autocomplete
from psql import (
    fetch,
    fetchrow,
    execute
)
from discord.ext import commands
import discord.ext
class BirthdayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @discord.ext.commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.command(name="setupbirthday", description="Setup birthday notifications")
    @is_whitelisted()
    @app_commands.describe(channel="The channel used for birthdays.", role="The role to ping for those wanting to know when a birthday happens.")
    async def birthdaysetup(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
        await interaction.response.defer()
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
                await interaction.followup.send(embed=embed, view=view, ephemeral=False)
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
            logger.exception("Error in /birthdaysetup command")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        
    @app_commands.command(name="setbirthday", description="Set your birthday (Once set, can't update for 3 months!)")
    @is_whitelisted()
    @app_commands.describe(birthdate="Month and day you're born.", time_zone="Timezone you live in")
    @app_commands.autocomplete(time_zone=timezone_autocomplete)
    async def setbirthday(self, interaction: Interaction, birthdate: str, time_zone: str):
        await interaction.response.defer()
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
                await interaction.followup.send("Cannot find server configuration.\nPlease have someone with manage guild permissions to use the /birthdaysetup command", ephemeral=False)
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
                
                embed = Embed(
                    title="Birthday Found",
                    color=Color.orange()
                )
                embed.add_field(
                    name="Current Birthday",
                    value=f"Date: {existing['birthdate']}\nTimezone: {existing['timezone'].replace("_", " ")}",
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
                        value=f"Date: {birthdate}\nTimezone: {time_zone.replace("_", " ")}",
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
                    embed = Embed(
                        title="Birthday Found",
                        color=Color.orange()
                    )
                    embed.add_field(
                        name="Current Birthday",
                        value=f"Date: {existing['birthdate']}\nTimezone: {existing['timezone'].replace("_", " ")}",
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
                        ephemeral=False
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
            
            embed = Embed(
                title="Birthday has been set!",
                color=Color(value=0xf8e7ef)
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
            
            await interaction.followup.send(embed=embed, ephemeral=False)
                
        except Exception as e:
            logger.exception("Error in /setbirthday command")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        
    @discord.ext.commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.command(name="removebirthday", description="Delete a user's birthday, effectively allowing them to use /setbirthday again.")
    @is_whitelisted()
    @app_commands.describe(user="The user to remove the birthday from.")
    async def removebirthday(self, interaction: Interaction, user: Member):
        await interaction.response.defer()
        try:
            existing = await fetchrow("""
                SELECT * FROM birthday_user WHERE guild_id = $1 AND user_id = $2
            """,
                interaction.guild.id,
                user.id
            )
            
            if not existing:
                await interaction.followup.send("User was not found in the existing database. If it's their first time, have them use /setbirthday.", ephemeral=True)
                return
            
            await execute("""
                DELETE FROM birthday_user WHERE guild_id = $1 and user_id = $2
            """,
                interaction.guild.id,
                user.id
            )
            
            await interaction.followup.send(f"{user.mention}'s birthday has been successfully removed.", ephemeral=False)
                
        except Exception as e:
            logger.exception("Error in /remove command")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    @app_commands.command(name="listbirthdays", description="Get a list of all the birthday's in this server")
    @is_whitelisted()
    async def list_birthdays(self, interaction: Interaction):
        await interaction.response.defer()
        try:
            hits = await fetch("""
                SELECT user_id, birthdate, timezone
                FROM birthday_user
                WHERE guild_id = $1
                ORDER BY birthdate
            """, 
                interaction.guild.id
            )
            
            cocoasguild = get_cocoasguild()
            personEmoji = utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else ''
            title_base = f"{personEmoji} Birthdays"
            
            if not hits:
                embed = Embed(
                    title=title_base,
                    color=Color(value=0xf8e7ef),
                    description="No birthdays found :("
                )
                await interaction.followup.send(embed=embed, ephemeral=False)
                return

            # Build pages
            CHUNK_SIZE = 25
            pages = []

            from handlers.buttons import PaginatorView
            for i in range(0, len(hits), CHUNK_SIZE):
                chunk = hits[i:i + CHUNK_SIZE]

                embed = Embed(
                    title=f"{title_base} - Page {len(pages)+1}",
                    color=Color(value=0xf8e7ef),
                    description="Here are all the users that have registered a birthday in this server:"
                )

                for hit in chunk:
                    user_id = hit['user_id']
                    birthdate = hit['birthdate']

                    # Requires server member intents
                    member = interaction.guild.get_member(user_id)
                    if member is None:
                        try:
                            # doesn't require server member intents but can be rate limited and slower
                            member = await interaction.guild.fetch_member(user_id)
                        except (Forbidden, HTTPException, NotFound):
                            # On any failure, just use user_id cleanly
                            username = str(user_id)
                        else:
                            username = member.display_name
                    else:
                        username = member.display_name
                    
                    line = f"**{username}** \u2022 **{birthdate}**"
                    embed.add_field(
                        name="\u200b",
                        value=line,
                        inline=True
                    )

                pages.append(embed)

            # Send first page with paginator view
            await interaction.followup.send(embed=pages[0], view=PaginatorView(interaction, pages), ephemeral=False)
                
        except Exception as e:
            logger.exception("Error in /listbirthdays command")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        
async def setup(bot):
    await bot.add_cog(BirthdayCog(bot))