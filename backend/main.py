# backend/main.py
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import logging

# Import the router from the api module
from .api import game_routes # Use relative import
# Import resource connection functions
from .core.cache import create_redis_pool, close_redis_pool, get_redis_connection
from .core.db_client import connect_db, close_db

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Application Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # === Startup Logic ===
    logger.info("--- Application starting up ---")

    # --- Connect Redis ---
    redis_pool_instance = None
    redis_instance = None
    try:
        logger.info("Attempting Redis connection setup...")
        redis_pool_instance = await create_redis_pool()
        redis_instance = get_redis_connection() # Get connection using the created pool
        setattr(app.state, 'redis_pool', redis_pool_instance)
        setattr(app.state, 'redis', redis_instance)
        logger.info("Redis pool created and attached to app state.")
    except Exception as e: # Catch any exception during Redis setup
        logger.error(f"Redis setup failed: {e}", exc_info=True)
        setattr(app.state, 'redis_pool', None)
        setattr(app.state, 'redis', None)

    # --- Connect Database ---
    db_pool_instance = None
    try:
        logger.info("Attempting DB connection setup...")
        db_pool_instance = await connect_db() # connect_db creates pool and runs setup_schema
        setattr(app.state, 'db_pool', db_pool_instance)
        logger.info("DB pool created and attached to app state.")
    except Exception as e: # Catch any exception during DB setup
        logger.error(f"Database setup failed: {e}", exc_info=True)
        setattr(app.state, 'db_pool', None)

    logger.info("--- Startup complete ---")
    # === End of Startup Logic ===

    yield # <<<--- SINGLE YIELD: Application runs here

    # === Shutdown Logic ===
    logger.info("--- Application shutting down ---")
    await close_redis_pool()
    await close_db()
    logger.info("--- Resources closed, shutdown complete ---")
    # === End of Shutdown Logic ===

# --- Create FastAPI App Instance ---
app = FastAPI(
    title="GenAI 'What Beats Rock' Game",
    description="""
    An interactive guessing game powered by Generative AI.
    Submit guesses to beat the current word and build a chain.
    Watch out for duplicates!
    """,
    version="0.1.0",
    lifespan=lifespan # Assign the lifespan manager
)

# --- Include Routers ---
app.include_router(game_routes.router)

# --- Root Endpoint ---
@app.get("/")
async def read_root(request: Request):
    logger.info("Root endpoint accessed.")
    # Use getattr for safer access to state attributes
    redis_pool = getattr(request.app.state, 'redis_pool', None)
    db_pool = getattr(request.app.state, 'db_pool', None)

    redis_available = redis_pool is not None
    db_available = db_pool is not None

    return {
        "message": "Welcome to the 'What Beats Rock?' GenAI Game API!",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "redis_connected": redis_available,
        "db_connected": db_available
    }

# --- Direct Run Block (for testing) ---
# Note: Lifespan logic runs correctly when using uvicorn command
if __name__ == "__main__":
    import uvicorn
    logger.warning("Running directly with __main__, use 'uvicorn backend.main:app' for production/proper lifespan.")
    # Uvicorn might handle lifespan differently when run programmatically like this vs command line
    uvicorn.run(app, host="127.0.0.1", port=8000)

logger.info("FastAPI app instance defined (module loaded).")