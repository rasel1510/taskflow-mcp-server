import asyncpg
from typing import Any, List, Optional, Dict
import config

_pool: Optional[asyncpg.Pool] = None

def get_clean_dsn(raw_url: str) -> str:
    """Strip Prisma-specific query params (sslmode, connect_timeout) so asyncpg connects cleanly."""
    if "?" in raw_url:
        return raw_url.split("?")[0]
    return raw_url

async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        clean_dsn = get_clean_dsn(config.DATABASE_URL)
        _pool = await asyncpg.create_pool(
            dsn=clean_dsn,
            ssl="require",
            min_size=1,
            max_size=10,
            command_timeout=30,
        )
        print("Connected to Neon PostgreSQL pool.")
    return _pool

async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        return await init_pool()
    return _pool

async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        print("Neon PostgreSQL pool closed.")

async def fetch_all(query: str, *args: Any) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *args)
        return [dict(r) for r in records]

async def fetch_one(query: str, *args: Any) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(query, *args)
        return dict(record) if record else None

async def fetch_val(query: str, *args: Any) -> Any:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)

async def execute(query: str, *args: Any) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)
