from discord import Interaction, app_commands
from psql import fetch

async def streamer_autocomplete(interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    rows = await fetch(
        "SELECT twitch_name FROM notification WHERE guild_id = $1",
        interaction.guild.id
    )

    # Filter by input if user started typing
    options = [
        app_commands.Choice(name=row["twitch_name"], value=row["twitch_name"])
        for row in rows if current.lower() in row["twitch_name"].lower()
    ]

    return options[:25]  # max 25