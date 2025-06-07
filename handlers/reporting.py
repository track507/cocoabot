import discord.ext
from datetime import datetime
from discord.ext import commands
from discord import app_commands
from discord.ui import Modal, TextInput
from helpers.constants import (
    is_whitelisted
)
from helpers.autocomplete import command_autocomplete
from handlers.logger import logger

class ReportBugModal(Modal, title="Bug Report"):
    def __init__(self, bot: commands.Bot, command: str):
        super().__init__(title="Bug Report")
        self.bot = bot
        self.command = command
        
        self.title_input = TextInput(
            label="Title",
            placeholder="Short title of your report (60 characters or less)",
            max_length=60
        )
        
        self.description_input = TextInput(
            label="Description",
            placeholder="Please describe the bug in detail",
            max_length=500,
            style=discord.TextStyle.paragraph
        )
        
        self.steps_input = TextInput(
            label="Steps to Reproduce",
            placeholder="How can I reproduce this bug?",
            max_length=500,
            style=discord.TextStyle.paragraph
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.steps_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        bug_channel_id=1374180371092078642
        bug_channel = self.bot.get_channel(bug_channel_id)
        embed = discord.Embed(
            title="New Bug Report",
            color=discord.Color.dark_purple()
        )
        embed.add_field(name="Command", value=self.command, inline=False)
        embed.add_field(name="Title", value=self.title_input.value, inline=False)
        embed.add_field(name="Description", value=self.description_input.value, inline=False)
        embed.add_field(name="Steps to Reproduce", value=self.steps_input.value, inline=False)
        embed.set_footer(text=f"Reported by {interaction.user}")
        embed.timestamp = datetime.now()
        from handlers.buttons import BugActionButton
        if bug_channel:
            await bug_channel.send(embed=embed, view=BugActionButton(self.bot, reporter=interaction.user))
        
        try:
            await interaction.user.send("Here's a copy of your bug report:", embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("I couldn't DM you a copy of your report.", ephemeral=True)

        await interaction.response.send_message("Bug report submitted!", ephemeral=True)

class RequestFeatureModal(Modal, title="Request Feature"):
    def __init__(self, bot: commands.Bot):
        super().__init__(title="Feature Request")
        self.bot = bot
        self.title_input = TextInput(
            label="Title",
            placeholder="Short title of your feature request (45 characters or less)",
            max_length=45
        )
        
        self.description_input = TextInput(
            label="Description",
            placeholder="Please describe the feature as best you can.",
            max_length=500,
            style=discord.TextStyle.paragraph
        )
        
        self.impact_input = TextInput(
            label="Impact",
            placeholder="How would this help others?",
            max_length=500,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.impact_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        feature_channel_id = 1374180371092078642
        feature_channel = self.bot.get_channel(feature_channel_id)
        embed = discord.Embed(
            title="New Feature Request",
            color=discord.Color.dark_purple()
        )
        embed.add_field(name="Title", value=self.title_input.value, inline=False)
        embed.add_field(name="Description", value=self.description_input.value, inline=False)
        embed.add_field(name="Impact", value=self.impact_input.value, inline=False)
        embed.set_footer(text=f"Requested by {interaction.user}")
        embed.timestamp = datetime.now()
        from handlers.buttons import FeatureRequestButton
        if feature_channel:
            await feature_channel.send(embed=embed, view=FeatureRequestButton(self.bot, reporter=interaction.user))
        
        try:
            await interaction.user.send("Here's a copy of your feature request:", embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("I couldn't DM you a copy of your request.", ephemeral=True)

        await interaction.response.send_message("Feature request submitted!", ephemeral=True)

class ReportingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @app_commands.command(name="bug", description="Report a bug.")
    @is_whitelisted()
    @app_commands.describe(command="Select which command is causing a bug.")
    @app_commands.autocomplete(command=command_autocomplete)
    async def bug(self, interaction: discord.Interaction, command: str):
        try:
            await interaction.response.send_modal(ReportBugModal(self.bot, command))
        except Exception as e:
            logger.exception("Error in /bug command")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            
    @app_commands.command(name="feature", description="Request a feature.")
    @is_whitelisted()
    async def feature(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(RequestFeatureModal(self.bot))
        except Exception as e:
            logger.exception("Error in /feature command")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            
async def setup(bot):
    await bot.add_cog(ReportingCog(bot))