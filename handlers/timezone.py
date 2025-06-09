from discord.ext import commands
from discord import app_commands, Interaction
from helpers.autocomplete import timezone_autocomplete
from handlers.logger import logger
from helpers.constants import (
    is_whitelisted,
)
from psql import (
    execute,
    fetchrow
)

class TimezoneCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="set_timezone", description="Set your local timezone (used for /schedule)")
    @is_whitelisted()
    @app_commands.describe(time_zone="Select a timezone you'd like to offset /schedule from")
    @app_commands.autocomplete(time_zone=timezone_autocomplete)
    async def set_timezone(self, interaction: Interaction, time_zone: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await execute("""
                UPDATE user_timezone
                SET timezone = $1
                WHERE user_id = $2
            """,
                time_zone,
                interaction.user.id
            )
            await interaction.followup.send(f"Your timezone has been updated to {time_zone}")
        except Exception as e:
            logger.exception("Error in /set_timezone command")
            await interaction.followup.send(f"❌ Error: {e}")
            
async def setup(bot):
    await bot.add_cog(TimezoneCog(bot))