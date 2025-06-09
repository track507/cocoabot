import pprint
from twitchAPI.object.eventsub import StreamOnlineEvent, StreamOfflineEvent
from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.type import AuthScope
from aiohttp import ClientTimeout
from handlers.logger import logger
from threading import Thread
import uvicorn
import discord
import asyncio
import helpers.constants as constants
from twitchAPI.twitch import Twitch
import handlers.errors as er
from psql import (
    fetch, 
    fetchrow, 
    execute, 
    fetchval,
    init_pool
)
from helpers.constants import (
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
    TWITCH_WEBHOOK_SECRET,
    COCOAS_GUILD_ID,
    PRIVATE_GUILD_ID,
    PUBLIC_URL
)
from web.webserver import app as fastapi_app

async def setup(bot):
    await init_pool()
    
    bot.add_listener(handle_stream_online, name="on_stream_online")
    bot.add_listener(handle_stream_offline, name="on_stream_offline")
    
    twitch = Twitch(app_id=TWITCH_CLIENT_ID, app_secret=TWITCH_CLIENT_SECRET, session_timeout=ClientTimeout(total=60))
    await initialize_twitch(twitch)
    
    logger.debug(f"TWITCH_WEBHOOK_SECRET: {TWITCH_WEBHOOK_SECRET} (type: {type(TWITCH_WEBHOOK_SECRET)})")
    logger.debug(f"twitch: {twitch} (type: {type(twitch)})")
    logger.info("Twitch object details:\n" + pprint.pformat(vars(twitch), indent=4))
    
    eventsub = EventSubWebhook(PUBLIC_URL, 8080, twitch, callback_loop=asyncio.get_running_loop())
    Thread(target=start_eventsub_thread, args=(eventsub,), daemon=True).start()
    logger.info("Started Twitch EventSub webhook on port 8080 in background thread")
    
    Thread(target=run_web_server, daemon=True).start()
    logger.info("Started FastAPI Web Server on port 8081 in background thread")
    
    await eventsub.unsubscribe_all() # remove all existing subscriptions to start fresh
    # iterate over eventSubScriptionResult.data which is a list of EventSubSubscription objects
    # and each EventSubSubscription object has an id and a condition attribute which is a dictionary [str, str]

    rows = await fetch("SELECT broadcaster_id FROM notification")
    for row in rows:
        await eventsub.listen_stream_online(
            broadcaster_user_id=row["broadcaster_id"],
            callback=handle_stream_online
        )
        await eventsub.listen_stream_offline(
            broadcaster_user_id=row["broadcaster_id"],
            callback=handle_stream_offline
        )
        
    logger.info(f"Finished registering {len(rows)} subscriptions.")
    
    constants.bot_state.bot = bot
    constants.bot_state.twitch = twitch
    constants.bot_state.eventsub = eventsub
    constants.bot_state.privateguild = discord.utils.get(bot.guilds, id=PRIVATE_GUILD_ID)
    constants.bot_state.cocoasguild = discord.utils.get(bot.guilds, id=COCOAS_GUILD_ID)
    constants.bot_state.tree = bot.tree
    er.setup_errors(bot.tree)
    logger.info(f"Setup complete.")
    
async def initialize_twitch(twitch: Twitch):
    try:
        from twitchAPI.type import AuthScope as AS
        USER_AUTH_SCOPES=[AS.CLIPS_EDIT]
        constants.bot_state.user_auth_scope = USER_AUTH_SCOPES
        assert isinstance(twitch, Twitch), "twitch is not an instance of Twitch"
        await twitch.authenticate_app([])
    except Exception as e:
            logger.exception("Error in initialize_twitch process")
    
def start_eventsub_thread(eventsub):
    eventsub.start()

def run_web_server():
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8081)
    
async def handle_stream_online(event: StreamOnlineEvent):
    data = event.event
    broadcaster_id = data.broadcaster_user_id
    logger.info(f"Broadcaster {broadcaster_id} went live.")

    async def process():
        try:
            is_already_live = await fetchval(
                "SELECT is_live FROM notification WHERE broadcaster_id = $1",
                broadcaster_id
            )

            if is_already_live:
                logger.info(f"Skipping already live broadcaster: {broadcaster_id}")
                return
            # Fetch stream info
            stream = None
            twitch = constants.get_twitch()
            async for s in twitch.get_streams(user_id=[broadcaster_id]):
                stream = s
                break

            """
            stream object
            2025-05-23T23:14:36.830 app[32876e00ad0978] dfw [info] 2025-05-23 23:14:36,830 [INFO] Stream object:
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 2025-05-23 23:14:36,831 [INFO] { 'game_id': '',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'game_name': '',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'id': '321493640444',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'is_mature': False,
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'language': 'en',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'started_at': datetime.datetime(2025, 5, 23, 23, 14, 15, tzinfo=tzutc()),
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'tag_ids': [],
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'tags': ['chill', 'Cozy', 'He', 'English'],
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'thumbnail_url': 'https://static-cdn.jtvnw.net/previews-ttv/live_user_lxchet-{width}x{height}.jpg',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'title': 'Testttt',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'type': 'live',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'user_id': '113142538',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'user_login': 'lxchet',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'user_name': 'Lxchet',
            2025-05-23T23:14:36.831 app[32876e00ad0978] dfw [info] 'viewer_count': 0}
            """

            if not stream:
                logger.warning(f"No stream found for broadcaster {broadcaster_id}")
                return

            title = stream.title.strip() if stream.title else "No stream title found"

            # Fetch rows of configured notification channels
            rows = await fetch(
                "SELECT channel_id, role_id FROM notification WHERE broadcaster_id = $1",
                broadcaster_id
            )

            await execute(
                "UPDATE notification SET is_live = TRUE WHERE broadcaster_id = $1",
                broadcaster_id
            )

            for row in rows:
                bot = constants.get_bot()
                channel = bot.get_channel(row["channel_id"])
                if not channel:
                    continue

                # Emojis
                cocoasguild = constants.get_cocoasguild()
                personEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLove") if cocoasguild else None
                streamEmoji = discord.utils.get(cocoasguild.emojis, name="cocoaLicense") if cocoasguild else None

                embed = discord.Embed(
                    title=f"🩷 {data.broadcaster_user_name} is LIVE",
                    url=f"https://twitch.tv/{data.broadcaster_user_login}",
                    color=discord.Color(value=0xf8e7ef)
                )
                embed.add_field(
                    name=f"{streamEmoji or ''} Title:",
                    value=title,
                    inline=False
                )
                embed.add_field(
                    name=f"<:cocoascontroller:1378540036437573734> Game:",
                    value=stream.game_name or "Unknown",
                    inline=False
                )
                
                embed.add_field(
                    name=f"{personEmoji or ''} Watch Now:",
                    value=f"https://twitch.tv/{data.broadcaster_user_login}",
                    inline=False
                )
                embed.set_footer(text="Stream started just now!")
                embed.timestamp = stream.started_at
                embed.set_thumbnail(
                    url=stream.thumbnail_url.replace("{width}", "320").replace("{height}", "180")
                )

                await channel.send(
                    content=f"<@&{row['role_id']}> https://twitch.tv/{data.broadcaster_user_login}",
                    embed=embed
                )

        except Exception as e:
            logger.exception("Error in handle_stream_online process")

    asyncio.create_task(process())

async def handle_stream_offline(event: StreamOfflineEvent):
    data = event.event
    broadcaster_id = data.broadcaster_user_id
    logger.info(f"Broadcaster {broadcaster_id} went offline.")

    async def process():
        try:
            await execute(
                "UPDATE notification SET is_live = FALSE WHERE broadcaster_id = $1",
                broadcaster_id
            )

        except Exception as e:
            logger.exception("Error in handle_stream_offline process")

    asyncio.create_task(process())