from discord import app_commands, Interaction
from helpers.constants import (
    get_tree
)
from psql import fetch

async def command_autocomplete(interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    tree = get_tree()
    commands = tree.get_commands()

    choices = [
        app_commands.Choice(name=cmd.name, value=cmd.name)
        for cmd in commands
        if current.lower() in cmd.name.lower()
    ]

    return choices[:25]

async def streamer_autocomplete(interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []
    
    try:
        rows = await fetch(
            "SELECT twitch_name FROM notification WHERE guild_id = $1",
            interaction.guild.id
        )
    except Exception:
        return []  # Return empty list if DB error

    options = [
        app_commands.Choice(name=row["twitch_name"], value=row["twitch_name"])
        for row in rows if current.lower() in row["twitch_name"].lower()
    ]

    return options[:25]

async def timezone_autocomplete(interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    import pytz
    all_timezones = pytz.all_timezones
    
    filtered = [tz for tz in all_timezones if current.lower() in tz.lower()]
    
    return [
        app_commands.Choice(name=tz, value=tz)
        for tz in filtered[:25]
    ]
    
async def video_types_autocomplete(interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    types = {
        "all": "All videos",
        "archive": "Get VOD's", 
        "highlight": "Get Highlights",
        "upload": "Get videos uploaded by cocoakissies"
    }
    
    if not current:
        filtered = types
    else:
        filtered = {k: v for k, v in types.items() if current.lower() in k.lower() or current.lower() in v.lower()}
    
    return [
        app_commands.Choice(name=desc, value=type_key)
        for type_key, desc in filtered.items()
    ]