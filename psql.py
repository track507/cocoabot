import asyncpg
import os
from handlers.logger import logger

_pool = None

async def init_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.getenv("DATABASE_URL"),
            min_size=1,
            max_size=10,
            command_timeout=60
        )
        logger.info("PostgreSQL connection pool initialized.")
    
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notification (
                broadcaster_id TEXT,
                twitch_name TEXT NOT NULL,
                twitch_link TEXT NOT NULL,
                role_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                is_live BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (broadcaster_id, guild_id)
            )
        """)
        logger.info("Notification table checked/created.")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS birthday_guild (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                role_id BIGINT NULL
            )
        """)
        logger.info("Birthday Guild table checked/created.")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS birthday_user (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                birthdate TEXT NOT NULL,
                timezone TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        logger.info("Birthday User table checked/created.")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_timezone (
                user_id BIGINT PRIMARY KEY,
                timezone TEXT NOT NULL
            )
        """)
        logger.info("User timezone table checked/created.")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS twitch_tokens (
                discord_user_id BIGINT PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
        """)
        logger.info("Twitch token table checked/created.")

def get_pool():
    if _pool is None:
        raise RuntimeError("Connection pool not initialized. Call init_pool() first.")
    return _pool

async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        logger.info("PostgreSQL connection pool closed.")
        _pool = None

async def execute(query: str, *args):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def fetch(query: str, *args):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def fetchrow(query: str, *args):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)

async def fetchval(query: str, *args):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)