import os
import discord
from discord import app_commands

PRIVATE_GUILD_ID = int(os.getenv("PRIVATE_GUILD_ID"))
COCOAS_GUILD_ID = int(os.getenv("COCOAS_GUILD_ID"))
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_WEBHOOK_SECRET = os.getenv("TWITCH_WEBHOOK_SECRET")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

WHITELISTED_GUILDS = {
    "COCOAS": COCOAS_GUILD_ID,
    "PRIVATE": PRIVATE_GUILD_ID
}
WHITELISTED_GUILD_IDS = set(WHITELISTED_GUILDS.values())

# Im sick of setting these
class BotState:
    def __init__(self):
        self.bot = None
        self.cocoasguild = None
        self.privateguild = None
        self.twitch = None
        self.eventsub = None
        self.tree = None
        self.user_auth_scope = None

# Global instance
bot_state = BotState()

# Convenience functions
def is_whitelisted():
    async def predicate(interaction: discord.Interaction):
        return interaction.guild and interaction.guild.id in WHITELISTED_GUILD_IDS
    return app_commands.check(predicate)

def get_cocoasguild():
    return bot_state.cocoasguild

def get_privateguild():
    return bot_state.privateguild

def get_twitch():
    return bot_state.twitch

def get_eventsub():
    return bot_state.eventsub

def get_bot():
    return bot_state.bot

def get_tree():
    return bot_state.tree

def get_twitch_auth_scope():
    return bot_state.user_auth_scope