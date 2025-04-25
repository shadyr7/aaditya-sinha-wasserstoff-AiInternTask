# backend/core/db_client.py
import asyncpg
import logging
import socket # Import socket for specific error checking
import os
logger = logging.getLogger(__name__)

# Global variable to hold the pool, accessible by other functions in this module
DB_POOL: asyncpg.Pool | None = None

# connect_db now accepts parameters and sets the global DB_POOL
async def connect_db(db_user: str, db_password: str | None, db_name: str, db_host: str, db_port: int):
    """Creates an asyncpg connection pool using provided parameters and sets the global pool."""
    global DB_POOL # Declare modification of global variable
    database_url = os.getenv("DATABASE_URL")
    # Construct DSN from arguments
    if database_url:
        if database_url.startswith("postgresql://"):
              database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        dsn = database_url
        logger.info(f"Attempting to connect to PostgreSQL using DATABASE_URL...")
    else:
         # Fallback to individual components
         logger.warning("DATABASE_URL not found, falling back to individual PG vars.")
         db_user = os.getenv("POSTGRES_USER", "user")
         db_password = os.getenv("POSTGRES_PASSWORD", "password")
         db_name = os.getenv("POSTGRES_DB", "whatbeatsrock_db")
         db_host = os.getenv("POSTGRES_HOST", "127.0.0.1")
         db_port = int(os.getenv("POSTGRES_PORT", 5432))
         dsn = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
         logger.info(f"Attempting to connect to PostgreSQL using individual vars at {db_host}:{db_port}...")

    try:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
        async with pool.acquire() as connection:
             await connection.execute("SELECT 1")
        DB_POOL = pool
        logger.info("Successfully connected to PostgreSQL and set global pool.")
        await setup_database_schema()
        return DB_POOL # Return pool
    except socket.gaierror as e:
        logger.error(f"Failed to resolve hostname used in DSN: {e}", exc_info=True)
        DB_POOL = None
        raise ConnectionError(f"Could not resolve PostgreSQL host") from e
    except asyncpg.exceptions.InvalidPasswordError as e:
        logger.error(f"Invalid PostgreSQL password.")
        DB_POOL = None
        raise ConnectionError("Invalid PostgreSQL password") from e
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}", exc_info=True)
        DB_POOL = None
        raise ConnectionError("Could not connect to PostgreSQL") from e



async def close_db():
    """Closes the global asyncpg connection pool."""
    global DB_POOL
    if DB_POOL:
        logger.info("Closing PostgreSQL connection pool.")
        await DB_POOL.close()
        DB_POOL = None
        logger.info("PostgreSQL pool closed.")
    else:
        logger.info("PostgreSQL pool already closed or was not initialized.")

async def get_db_pool() -> asyncpg.Pool:
    """Returns the existing global database connection pool."""
    if DB_POOL is None:
        logger.error("DB Pool is not initialized!")
        raise ConnectionError("Database pool not initialized. Check startup logs.")
    return DB_POOL

async def setup_database_schema():
    """Creates the necessary table(s) if they don't exist, using the global pool."""
    # This function now relies on DB_POOL being set globally by connect_db
    pool = await get_db_pool() # Get the global pool
    logger.info("Setting up database schema...")
    try:
        async with pool.acquire() as connection:
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS global_guess_counts (
                    word TEXT PRIMARY KEY,
                    guess_count INTEGER NOT NULL DEFAULT 1
                );
            """)
        logger.info("Database schema setup complete (or table already exists).")
    except Exception as e:
        logger.error(f"Failed to setup database schema: {e}", exc_info=True)
        # Decide if failure here should prevent startup? For now, just log.


async def increment_global_guess_count(word: str) -> int | None:
    """
    Increments the global guess count for a given word (case-insensitive), using the global pool.
    Returns the new count, or None if the operation fails.
    """
    pool = await get_db_pool() # Get the global pool
    normalized_word = word.lower().strip()
    if not normalized_word:
        logger.warning("Attempted to increment count for empty word.")
        return None

    logger.debug(f"Incrementing global count for word: '{normalized_word}'")
    try:
        async with pool.acquire() as connection:
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