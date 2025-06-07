from psql import fetch, fetchrow
from handlers.logger import logger
from datetime import datetime
import pytz
import discord

async def check_birthdays():
    from helpers.constants import bot
    utc_now = datetime.now()
    hits = await fetch("""
        SELECT * FROM birthday_user
    """)
    
    guild_ids = set()
    
    for row in hits:
        guild_id = row['guild_id']
        user_id = row['user_id']
        birthdate = row['birthdate']
        timezone_str = row['timezone']
        
        try:
            tz = pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone for user {user_id} in guild {guild_id}: {timezone_str}")
            continue
        
        user_now = utc_now.replace(tzinfo=pytz.utc).astimezone(tz)
        today_str = user_now.strftime("%m-%d")
        hour_now = user_now.hour
        
        if today_str == birthdate and hour_now == 0:
            guild = bot.get_guild(guild_id)
            if guild is not None:
                guild_ids.add(guild_id)
    
    if guild_ids:
        return list(guild_ids)
    else:
        return None
    
async def announce_birthday(hits):
    from helpers.constants import bot, cocoasguild
    guild_birthdays = {}
    
    for bd in hits:
        guild_id = bd['guild_id']
        user_id = bd['user_id']
        
        if guild_id not in guild_birthdays:
            guild_birthdays[guild_id] = []
        
        guild_birthdays[guild_id].append({
            "user_id": user_id,
        })
        
    # send one message per guild.
    for guild_id, users in guild_birthdays.items():
        # guild object
        guild = bot.get_guild(guild_id)
        if not guild:
            continue
        
        # get guild config
        config = await fetchrow("""
            SELECT * FROM birthday_guild WHERE guild_id = $1
        """,
            guild_id
        )
        
        # check if the channel has been deleted.
        channel = guild.get_channel(config['channel_id'])
        if not channel:
            continue
        
        # check if the role has been deleted.
        role_mention = ""
        if config['role_id']:
            role = guild.get_role(config['role_id'])
            if role:
                role_mention = role.mention
        
        personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else None
        # build the embed
        embed = discord.Embed(
            title=f"{personEmoji} Today is the following user(s) birthdays!",
            color=discord.Color.gold()
        )
        
        for user in users:
            # Check if the user is still in the server.
            member = guild.get_member(user_id)
            if not member:
                continue
            
            line = f"{member.mention}"
                
            embed.add_field(
                name="\u200b",
                value=line,
                inline=False
            )
            
        embed.set_footer(text="Happy Birthday!!!")
        embed.timestamp = datetime.now()
        await channel.send(
            content=role_mention if role_mention else None,
            embed=embed
        )