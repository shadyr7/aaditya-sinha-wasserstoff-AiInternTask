# backend/core/cache.py
import redis.asyncio as redis # Use the async version
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv() # Load environment variables from .env file

# --- Redis Connection Pool ---
# Global variable to hold the connection pool
# We initialize it to None and connect in the app lifespan
redis_pool = None

async def create_redis_pool():
    """Creates an async Redis connection pool."""
    global redis_pool
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    try:
        logger.info(f"Attempting to connect to Redis at {redis_host}:{redis_port}, DB: {redis_db}")
        # decode_responses=True makes redis-py return strings instead of bytes
        redis_pool = redis.ConnectionPool.from_url(
            f"redis://{redis_host}:{redis_port}/{redis_db}",
            decode_responses=True,
            max_connections=20 # Configure max connections as needed
        )
        # Test connection
        async with redis.Redis(connection_pool=redis_pool) as r:
            await r.ping()
        logger.info("Successfully connected to Redis and pinged.")
        return redis_pool
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
        # Depending on requirements, you might exit the app or run in a degraded mode
        raise ConnectionError("Could not connect to Redis") from e

async def close_redis_pool():
    """Closes the Redis connection pool."""
    global redis_pool
    if redis_pool:
        logger.info("Closing Redis connection pool.")
        # Note: redis-py's async pool doesn't have an explicit close method like the sync one.
        # Connections are managed automatically. We mainly set the global var to None.
        # For more explicit cleanup if needed, manage individual connections, but pool is generally preferred.
        redis_pool = None # Allow garbage collection
        logger.info("Redis pool reference removed.")

def get_redis_connection() -> redis.Redis:
    """Gets a Redis connection instance from the pool."""
    if redis_pool is None:
        # This should ideally not happen if lifespan manager is used correctly
        logger.error("Redis pool is not initialized!")
        # Depending on strictness, you could raise an error here
        # For now, let's attempt a fallback connection (not recommended for production)
        # raise ConnectionError("Redis pool not initialized")
        # Fallback (less ideal): return redis.Redis.from_url(...)
        # Best approach: Ensure lifespan initializes it.
        raise ConnectionError("Redis pool not initialized. Check application lifespan.")

    # Create a new client instance using the shared pool
    return redis.Redis(connection_pool=redis_pool)