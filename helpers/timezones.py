from discord import app_commands, Interaction
import pytz

async def timezone_autocomplete(interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    all_timezones = pytz.all_timezones
    
    filtered = [tz for tz in all_timezones if current.lower() in tz.lower()]
    
    return [
        app_commands.Choice(name=tz, value=tz)
        for tz in filtered[:25]
    ]
