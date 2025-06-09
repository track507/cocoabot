import discord
from discord import app_commands
from handlers.logger import logger

# TODO: Turn this into a cog
def setup_errors(tree):
    @tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            await interaction.response.send_message(
                f"❌ You are missing the following permission(s) to use this command: `{missing_perms}`",
                ephemeral=True
            )
        else:
            logger.exception("Unhandled application command error", exc_info=error)
            try:
                await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)