# backend/core/db_client.py
import asyncpg
import os
import logging
import socket

logger = logging.getLogger(__name__)

# --- Module-level variable for the pool ---
DB_POOL: asyncpg.Pool | None = None
# --- End module-level variable ---

async def connect_db():
    """
    Connects to the PostgreSQL database using environment variables,
    sets the module-level DB_POOL, and runs initial schema setup.
    Prefers DATABASE_URL if available.
    """
    global DB_POOL # Indicate modification of module-level variable

    # Prevent reconnecting if already connected
    if DB_POOL and not DB_POOL._closed:
         logger.info("Database pool already exists and is active. Reusing.")
         # Consider optionally running setup_schema again on reconnect/reuse if needed
         # await setup_database_schema()
         return DB_POOL

    # Determine connection DSN
    database_url = os.getenv("DATABASE_URL")
    if database_url:
         if database_url.startswith("postgresql://"):
              database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
         dsn = database_url
         logger.info(f"Attempting DB connection using DATABASE_URL...")
    else:
         logger.warning("DATABASE_URL not found, falling back to individual PG vars.")
         db_user = os.getenv("POSTGRES_USER", "user")
         db_password = os.getenv("POSTGRES_PASSWORD", "password")
         db_name = os.getenv("POSTGRES_DB", "whatbeatsrock_db")
         db_host = os.getenv("POSTGRES_HOST", "127.0.0.1") # Default to IP for local safety
         db_port = int(os.getenv("POSTGRES_PORT", 5432))
         dsn = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
         logger.info(f"Attempting DB connection using individual vars (Host: {db_host})...")

    # Establish connection pool
    try:
        pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=10,
            timeout=15, # Add connection timeout
            command_timeout=10 # Add command timeout
        )
        # Test connection before assigning globally
        async with pool.acquire() as connection:
             await connection.execute("SELECT 1")

        DB_POOL = pool # Assign to module-level variable
        logger.info("Successfully connected to PostgreSQL and set DB_POOL.")

        # Setup schema using the newly created pool
        await setup_database_schema()

        return DB_POOL # Return the pool

    except (socket.gaierror, OSError) as e: # Catch resolution/network errors
        logger.error(f"Network/Resolution error connecting to PostgreSQL: {e}", exc_info=True)
        DB_POOL = None
        raise ConnectionError(f"Could not resolve/connect to PostgreSQL host") from e
    except asyncpg.exceptions.InvalidPasswordError as e:
        logger.error(f"Invalid PostgreSQL password.")
        DB_POOL = None
        raise ConnectionError("Invalid PostgreSQL password") from e
    except Exception as e:
        logger.error(f"Failed to connect or setup PostgreSQL: {e}", exc_info=True)
        DB_POOL = None # Ensure pool is None on any failure
        raise ConnectionError("Could not connect/setup PostgreSQL") from e


async def setup_database_schema():
    """Creates the necessary table(s) if they don't exist, using the global pool."""
    logger.info("Attempting database schema setup...")
    # Use get_db_pool to ensure the pool exists before proceeding
    pool = await get_db_pool()
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
        # Decide if this should halt startup? Re-raising makes it fatal.
        raise ConnectionError("Failed to setup database schema") from e


async def close_db():
    """Closes the module-level asyncpg connection pool."""
    global DB_POOL
    if DB_POOL and not DB_POOL._closed:
        logger.info("Closing PostgreSQL connection pool.")
        try:
             await DB_POOL.close()
             logger.info("PostgreSQL pool closed successfully.")
        except Exception as e:
             logger.error(f"Error closing PostgreSQL pool: {e}", exc_info=True)
        finally:
             DB_POOL = None # Ensure it's marked as None even if close fails
    else:
        logger.info("PostgreSQL pool already closed or was not initialized.")


async def get_db_pool() -> asyncpg.Pool:
    """Safely returns the existing module-level database connection pool."""
    if DB_POOL is None:
        logger.error("DB_POOL is None when requested!")
        raise ConnectionError("Database pool not initialized. Check startup logs for errors.")
    if DB_POOL._closed:
         logger.error("DB_POOL was closed when requested!")
         raise ConnectionError("Database pool was closed unexpectedly.")
    return DB_POOL


async def increment_global_guess_count(word: str) -> int | None:
    """Increments the global guess count, using the safely retrieved global pool."""
    try:
        # Get the pool safely at the start of the operation
        pool = await get_db_pool()
        normalized_word = word.lower().strip()
        if not normalized_word:
            logger.warning("Attempted to increment count for empty word.")
            return None

        logger.debug(f"Incrementing global count for word: '{normalized_word}'")
        async with pool.acquire() as connection:
            new_count = await connection.fetchval("""
                INSERT INTO global_guess_counts (word, guess_count)
                VALUES ($1, 1)
                ON CONFLICT (word) DO UPDATE SET
                    guess_count = global_guess_counts.guess_count + 1
                RETURNING guess_count;
            """, normalized_word)
        logger.info(f"Global count for '{normalized_word}' is now {new_count}.")
        return new_count
    except ConnectionError as e: # Catch if get_db_pool failed
         logger.error(f"Cannot increment count: {e}")
         return None
    except Exception as e:
        # Catch potential DB errors during acquire or fetchval
        logger.error(f"Error incrementing global count for '{normalized_word}': {e}", exc_info=True)
        return None