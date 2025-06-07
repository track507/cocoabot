from discord.ext import commands
from discord import app_commands, Interaction
import helpers.timezonesac as tz
from handlers.logger import logger
from helpers.constants import (
    is_whitelisted,
)
from psql import (
    execute
)

class TimezoneCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="set_timezone", description="Set your local timezone (used for /schedule)")
    @is_whitelisted()
    @app_commands.describe(time_zone="Select a timezone you'd like to offset /schedule from")
    @app_commands.autocomplete(time_zone=tz.timezone_autocomplete)
    async def set_timezone(self, interaction: Interaction, time_zone: str):
        try:
            await execute("""
                INSERT INTO user_timezone (user_id, timezone)
                VALUES ($1, $2)
            """,
                interaction.user.id,
                time_zone
            )
            await interaction.response.send_message(f"Your timezone has been set to {time_zone}")
        except Exception as e:
            logger.exception("Error in /set_timezone command")
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)