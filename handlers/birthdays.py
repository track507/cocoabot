from discord.ext import commands
from discord import HTTPException, app_commands, Interaction, Embed, utils, Color, NotFound, Forbidden
from handlers.logger import logger
from helpers.constants import (
    is_whitelisted,
    get_cocoasguild
)
from psql import (
    fetch
)

class BirthdayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
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