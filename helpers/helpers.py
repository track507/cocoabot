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
import os

async def setup(bot):
    
    bot.add_listener(handle_stream_online, name="on_stream_online")
    bot.add_listener(handle_stream_offline, name="on_stream_offline")
    
    twitch = Twitch(app_id=TWITCH_CLIENT_ID, app_secret=TWITCH_CLIENT_SECRET, session_timeout=ClientTimeout(total=60))
    await initialize_twitch(twitch)
    
    logger.debug(f"TWITCH_WEBHOOK_SECRET: {TWITCH_WEBHOOK_SECRET} (type: {type(TWITCH_WEBHOOK_SECRET)})")
    logger.debug(f"twitch: {twitch} (type: {type(twitch)})")
    logger.info("Twitch object details:\n" + pprint.pformat(vars(twitch), indent=4))
    
    webhook_port = int(os.getenv('PORT', 8080))
    logger.info(f"Setting up EventSub webhook on port {webhook_port}")
    
    eventsub = EventSubWebhook(
        callback_url=PUBLIC_URL,
        port=webhook_port,
        twitch=twitch,
        callback_loop=asyncio.get_running_loop()
    )
    
    if TWITCH_WEBHOOK_SECRET:
        eventsub._secret = TWITCH_WEBHOOK_SECRET.encode('utf-8') if isinstance(TWITCH_WEBHOOK_SECRET, str) else TWITCH_WEBHOOK_SECRET
        logger.info("Webhook secret configured")
    else:
        logger.error("TWITCH_WEBHOOK_SECRET not found in environment variables!")
        raise ValueError("TWITCH_WEBHOOK_SECRET is required")
    
    # Start EventSub in background thread with better error handling
    def start_eventsub_with_retry():
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info(f"Starting EventSub webhook (attempt {retry_count + 1}/{max_retries})")
                eventsub.start()
                break
            except OSError as e:
                if e.errno == 98:  # Address already in use
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"Port {webhook_port} in use, retrying in 5 seconds...")
                        import time
                        time.sleep(5)
                    else:
                        logger.error(f"Failed to bind to port {webhook_port} after {max_retries} attempts")
                        raise
                else:
                    raise
            except Exception as e:
                logger.exception("Failed to start EventSub webhook")
                raise
    
    Thread(target=start_eventsub_with_retry, daemon=True).start()
    
    # Wait a bit for the webhook to start
    await asyncio.sleep(2)
    
    logger.info(f"Started Twitch EventSub webhook on port {webhook_port} in background thread")
    logger.info(f"Webhook URL: {PUBLIC_URL}")
    logger.info(f"Eventsub secret configured: {eventsub._secret is not None}")
    
    # Clean up existing subscriptions
    try:
        await eventsub.unsubscribe_all()
        logger.info("Cleaned up existing EventSub subscriptions")
    except Exception as e:
        logger.warning(f"Could not clean up existing subscriptions: {e}")
    
    # Initialize bot state
    constants.bot_state.bot = bot
    constants.bot_state.twitch = twitch
    constants.bot_state.eventsub = eventsub
    constants.bot_state.privateguild = discord.utils.get(bot.guilds, id=PRIVATE_GUILD_ID)
    constants.bot_state.cocoasguild = discord.utils.get(bot.guilds, id=COCOAS_GUILD_ID)
    constants.bot_state.tree = bot.tree
    er.setup_errors(bot.tree)
    
    # Set up subscriptions with retry logic
    rows = await fetch("SELECT broadcaster_id FROM notification")
    successful_subs = 0
    failed_subs = 0
    
    for row in rows:
        try:
            logger.info(f"Setting up subscriptions for broadcaster {row['broadcaster_id']}")
            
            # Add delays between subscription attempts
            await asyncio.sleep(1)
            
            await eventsub.listen_stream_online(
                broadcaster_user_id=row["broadcaster_id"],
                callback=handle_stream_online
            )
            
            await asyncio.sleep(0.5)
            
            await eventsub.listen_stream_offline(
                broadcaster_user_id=row["broadcaster_id"],
                callback=handle_stream_offline
            )
            
            successful_subs += 1
            logger.info(f"Successfully set up subscriptions for broadcaster {row['broadcaster_id']}")
            
        except Exception as e:
            failed_subs += 1
            logger.error(f"Failed to set up subscriptions for broadcaster {row['broadcaster_id']}: {e}")
            # Continue with other subscriptions instead of failing completely
    
    logger.info("Validating bot state...")
    required_components = [
        ("bot", constants.get_bot()),
        ("twitch", constants.get_twitch()),
        ("eventsub", constants.get_eventsub()),
        ("cocoasguild", constants.get_cocoasguild()),
        ("tree", constants.get_tree())
    ]
    
    missing = [name for name, component in required_components if component is None]
    if missing:
        raise RuntimeError(f"Setup incomplete - missing components: {missing}")
    
    logger.info("All bot components properly initialized")
    logger.info(f"EventSub subscriptions: {successful_subs} successful, {failed_subs} failed")
    logger.info(f"Setup complete.")
    
async def initialize_twitch(twitch: Twitch):
    try:
        from twitchAPI.type import AuthScope as AS
        from twitchAPI.helper import first
        USER_AUTH_SCOPES=[AS.CLIPS_EDIT]
        constants.bot_state.user_auth_scope = USER_AUTH_SCOPES
        assert isinstance(twitch, Twitch), "twitch is not an instance of Twitch"
        await twitch.authenticate_app([])
        
        # Log current subscriptions for debugging
        try:
            current_subs = await twitch.get_eventsub_subscriptions()
            subs = current_subs.data
            logger.info(f"Current EventSub subscriptions: {len(subs)}")
            
            if len(subs) == 0 or current_subs.total == 0: 
                logger.info("No existing subscriptions found")
                return
                
            for sub in subs:
                user_id = sub.condition.get('broadcaster_user_id') or sub.condition.get('user_id')
                if not user_id:
                    logger.warning(f"Subscription {sub.id} has no broadcaster/user ID in condition")
                    continue

                user_info = await first(twitch.get_users(user_ids=[user_id]))
                if user_info:
                    display_name = user_info.display_name
                    logger.info(f"Existing subscription - Broadcaster: {user_id} ({display_name}), Type: {sub.type}, Status: {sub.status}")
                else:
                    logger.info(f"Existing subscription - Broadcaster: {user_id} (user not found), Type: {sub.type}, Status: {sub.status}")
        except Exception as e:
            logger.warning(f"Could not fetch existing subscriptions: {e}")
            
    except Exception as e:
        logger.exception("Error in initialize_twitch process")

async def handle_stream_online(event: StreamOnlineEvent):
    data = event.event
    broadcaster_id = data.broadcaster_user_id
    logger.info(f"Broadcaster {broadcaster_id} went live.")

    async def process():
        try:
            if not all([constants.get_twitch(), constants.get_bot(), constants.get_cocoasguild()]):
                logger.error(f"Bot state not initialized when handling stream online for {broadcaster_id}")
                return
                
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