# Import from libraries
from twitchAPI.helper import first
import discord, asyncio
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Import from files
import helpers.constants as constants
from handlers.logger import logger
from psql import (
    init_pool,
    close_pool
)
from helpers.helpers import (
    setup,
)
from helpers.constants import (
    is_whitelisted,
    DISCORD_TOKEN
)

load_dotenv()

"""
    I know I can use discord webhook in the discord developer portal but at that point it was a sunk cost...
"""

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# startup
@bot.event
async def on_ready():
    await setup(bot)
    await load_cogs()

    logger.info(f"Logged in as {bot.user}")
    await tree.sync()
        
# About
@tree.command(name="about", description="About the bot.")
@is_whitelisted()
async def about(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        cocoasguild = constants.get_cocoasguild()
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
                "\n\u2022 Getting Cocoa's schedule for the next 5 streams"
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
                "[GitHub](https://github.com/track507/cocoabot/issues) or use the `/bug` command."
            ),
            inline=False
        )
        embed.add_field(
            name="<:cocoascontroller:1378540036437573734> Features & Suggestions",
            value=(
                "Have ideas for new features? Open an issue with the `enhancement` label on "
                "[GitHub](https://github.com/track507/cocoabot/issues) or use the `/feature` command."
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
        await interaction.followup.send(embed=embed, ephemeral=False)
    except Exception as e:
        logger.exception("About failed")
        await interaction.followup.send(f"❌ About failed: `{str(e)}`", ephemeral=True)

async def load_cogs():
    await bot.load_extension("handlers.twitch")
    await bot.load_extension("handlers.timezone")
    await bot.load_extension("handlers.tests")
    await bot.load_extension("handlers.reporting")
    await bot.load_extension("handlers.birthdays")

async def main():
    try:
        await init_pool()
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