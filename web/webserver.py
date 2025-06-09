from fastapi import FastAPI, Request
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

@app.post("/callback")
async def twitch_eventsub_callback(request: Request):
    from helpers.constants import get_eventsub
    body = await request.body()
    headers = dict(request.headers)

    # Forward to EventSubWebhook's request handler
    response = get_eventsub().handle_eventsub_request(body, headers)

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=response.headers
    )

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