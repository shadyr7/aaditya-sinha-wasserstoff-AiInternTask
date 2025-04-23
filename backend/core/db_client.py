# backend/core/db_client.py
import asyncpg
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

DB_POOL = None

async def connect_db():
    """Creates an asyncpg connection pool."""
    global DB_POOL
    db_user = os.getenv("POSTGRES_USER", "user")
    db_password = os.getenv("POSTGRES_PASSWORD", "password")
    db_name = os.getenv("POSTGRES_DB", "whatbeatsrock_db")
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", 5432)

    dsn = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    logger.info(f"Attempting to connect to PostgreSQL at {db_host}:{db_port}...")

    try:
        DB_POOL = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1, # Minimum number of connections in the pool
            max_size=10 # Maximum number of connections
        )
        # Optional: Test connection with a simple query
        async with DB_POOL.acquire() as connection:
             await connection.execute("SELECT 1")
        logger.info("Successfully connected to PostgreSQL and created pool.")
        await setup_database_schema() # Create table if needed
        return DB_POOL
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}", exc_info=True)
        DB_POOL = None # Ensure pool is None if connection fails
        raise ConnectionError("Could not connect to PostgreSQL") from e

async def close_db():
    """Closes the asyncpg connection pool."""
    global DB_POOL
    if DB_POOL:
        logger.info("Closing PostgreSQL connection pool.")
        await DB_POOL.close()
        DB_POOL = None
        logger.info("PostgreSQL pool closed.")

async def get_db_pool() -> asyncpg.Pool:
    """Returns the existing database connection pool."""
    if DB_POOL is None:
        # Should ideally be handled by lifespan/readiness checks
        logger.error("DB Pool is not initialized!")
        raise ConnectionError("Database pool not initialized.")
    return DB_POOL

async def setup_database_schema():
    """Creates the necessary table(s) if they don't exist."""
    if not DB_POOL:
        logger.error("Cannot set up schema, DB pool not initialized.")
        return

    logger.info("Setting up database schema...")
    async with DB_POOL.acquire() as connection:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS global_guess_counts (
                word TEXT PRIMARY KEY,
                guess_count INTEGER NOT NULL DEFAULT 1
            );
        """)
    logger.info("Database schema setup complete (or table already exists).")


async def increment_global_guess_count(word: str) -> int | None:
    """
    Increments the global guess count for a given word (case-insensitive).
    Returns the new count, or None if the operation fails.
    """
    if not DB_POOL:
        logger.error("Cannot increment count, DB pool not initialized.")
        return None

    normalized_word = word.lower().strip() # Store and query lowercase/stripped
    if not normalized_word:
        logger.warning("Attempted to increment count for empty word.")
        return None

    logger.debug(f"Incrementing global count for word: '{normalized_word}'")
    try:
        async with DB_POOL.acquire() as connection:
            # Atomically insert or update the count
            new_count = await connection.fetchval("""
                INSERT INTO global_guess_counts (word, guess_count)
                VALUES ($1, 1)
                ON CONFLICT (word) DO UPDATE SET
                    guess_count = global_guess_counts.guess_count + 1
                RETURNING guess_count;
            """, normalized_word)
            logger.info(f"Global count for '{normalized_word}' is now {new_count}.")
            return new_count
    except Exception as e:
        logger.error(f"Error incrementing global count for '{normalized_word}': {e}", exc_info=True)
        return None # Indicate failure