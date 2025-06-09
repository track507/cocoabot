from fastapi import FastAPI, Request, Response
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from helpers.constants import get_twitch
from handlers.logger import logger

app = FastAPI()

# setup callback to store the user token.
@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    try:
        from helpers.constants import get_twitch_auth_scope
        full_url = str(request.url)
        twitch = get_twitch()
        # ! required permission to create clips, might move this to constants w/ getter
        # * https://dev.twitch.tv/docs/api/reference/#create-clip 
        # * https://pytwitchapi.dev/en/stable/modules/twitchAPI.twitch.html#twitchAPI.twitch.Twitch.create_clip
        TARGET_SCOPE = get_twitch_auth_scope()
        auth = UserAuthenticator(twitch, TARGET_SCOPE, force_verify=False)
        token, refresh_token, expires_in = auth.validate_auth_response_url(full_url)
        discord_user_id = request.query_params.get('state')
        if not discord_user_id:
            return "Missing state parameter."
        await store_user_authentication(discord_user_id, token, refresh_token, expires_in)
        
        logger.info(f"Authorized Discord user {discord_user_id} with Twitch token.")
    except Exception as e:
        logger.info(f"OAuth callback error: {e}")
        return f"Error in OAuth callback: {e}"

@app.post("/twitch/eventsub/callback")
async def twitch_eventsub_callback(request: Request):
    import hmac, json
    from helpers.constants import TWITCH_WEBHOOK_SECRET
    from helpers.helpers import (
        handle_stream_offline,
        handle_stream_online
    )
    from twitchAPI.object.eventsub import StreamOnlineEvent, StreamOfflineEvent
    
    body_bytes = await request.body()
    print(f"Callback body: {body_bytes}")

    headers = request.headers
    print(f"Callback headers: {headers}")
    
    # Notification request headers
    TWITCH_MESSAGE_ID = "Twitch-Eventsub-Message-Id".lower()
    TWITCH_MESSAGE_TIMESTAMP = "Twitch-Eventsub-Message-Timestamp".lower()
    TWITCH_MESSAGE_SIGNATURE = "Twitch-Eventsub-Message-Signature".lower()
    
    # not part of hmac
    message_type = headers["Twitch-Eventsub-Message-Type"]
    
    hmac_prefix = 'sha256='
    
    # HMAC must be in this order
    # build message used to get the HMAC.
    msg = request.headers[TWITCH_MESSAGE_ID] + request.headers[TWITCH_MESSAGE_TIMESTAMP] + body_bytes
    # compute the hmac
    hmac_computed = hmac_prefix + hmac.new('sha256', TWITCH_WEBHOOK_SECRET).update(msg).digest('hex')
    
    if not hmac.compare_digest(hmac_computed, request.headers[TWITCH_MESSAGE_SIGNATURE]):
        logger.warning("Invalid Twitch EventSub signature")
        return Response(status_code=403)

    json_body = json.loads(body_bytes)

    # Process message
    if message_type == "webhook_callback_verification":
        challenge = json_body["challenge"]
        logger.info(f"Twitch EventSub verification: {challenge}")
        return Response(content=challenge, media_type="text/plain")

    if message_type == "notification":
        event_type = json_body["subscription"]["type"]
        event_payload = json_body["event"]

        logger.info(f"Received Twitch EventSub event: {event_type} → {event_payload}")

        if event_type == "stream.online":
            await handle_stream_online(StreamOnlineEvent(event=json_body["event"]))
        elif event_type == "stream.offline":
            await handle_stream_offline(StreamOfflineEvent(event=json_body["event"]))

        return Response(status_code=204)

    return Response(status_code=204)

# async func to store user in DB
async def store_user_authentication(discord_user_id, access_token, refresh_token, expires_in):
    try:
        from datetime import datetime, timedelta
        from psql import execute
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        await execute("""
            INSERT INTO twitch_tokens (discord_user_id, access_token, refresh_token, expires_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (discord_user_id) DO UPDATE
            SET access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at
        """, discord_user_id, access_token, refresh_token, expires_at)
    except Exception as e:
        logger.info(f"Store user authentication error: {e}")
        return f"Error in storing user authentication: {e}"

async def get_user_authentication(discord_user_id):
    try:
        from psql import fetchrow
        return await fetchrow("""
            SELECT access_token, refresh_token, expires_at FROM twitch_tokens WHERE discord_user_id = $1
        """,
            discord_user_id
        )
    except Exception as e:
        logger.info(f"Get user authentication error: {e}")
        return None

async def refresh_user_token(discord_user_id, refresh_token, app_id, app_secret):
    try:
        from twitchAPI.oauth import refresh_access_token
        from datetime import datetime, timedelta
        from psql import execute
        new_access_token, new_refresh_token, new_expires_in = await refresh_access_token(
            refresh_token, app_id, app_secret
        )
        new_expires_at = datetime.now() + timedelta(seconds=new_expires_in)
        await execute("""
            UPDATE twitch_tokens
            SET access_token = $1,
                refresh_token = $2,
                expires_at = $3
            WHERE discord_user_id = $4
        """, new_access_token, new_refresh_token, new_expires_at, discord_user_id)
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "expires_at": new_expires_at
        }
        
    except Exception as e:
        logger.exception(f"Refresh user token error: {e}")
        return None

async def is_valid_token(access_token):
    try:
        from twitchAPI.oauth import validate_token
        return await validate_token(access_token)
    except Exception as e:
        logger.exception(f"Valid user token error: {e}")
        return False