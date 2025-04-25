# backend/main.py
import logging
import os # Import os for getenv
from dotenv import load_dotenv

# --- Load .env FIRST ---
load_dotenv()
# Configure logging AFTER load_dotenv, BEFORE first use
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Environment variables loaded from .env (if present). Logging configured.")
# --- End Load .env & Logging Config ---

from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from .core.limiter import limiter, update_limiter_storage
from .api import game_routes # Use relative import
# Import resource connection functions
from .core.cache import create_redis_pool, close_redis_pool, get_redis_connection
# Import only connect_db and close_db as we call them directly
from .core.db_client import connect_db, close_db
from starlette.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
# --- Initialize Rate Limiter ---
# Uses the Redis connection established in lifespan
# limiter = Limiter(key_func=get_remote_address, storage_uri="memory://") # Temp storage, will use redis later

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
        # Check if pool creation was successful before getting connection
        if redis_pool_instance:
             redis_instance = get_redis_connection()
             setattr(app.state, 'redis_pool', redis_pool_instance)
             setattr(app.state, 'redis', redis_instance)
             logger.info("Redis pool created and attached to app state.")
             redis_host = os.getenv("REDIS_HOST", "localhost")
             redis_port = int(os.getenv("REDIS_PORT", 6379))
             redis_db = int(os.getenv("REDIS_DB", 0))
             redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
             update_limiter_storage(redis_url)
             global limiter
             limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url)
             app.state.limiter = limiter # Make limiter accessible via state
             logger.info(f"Rate limiter configured to use Redis: {redis_url}")
        else:
             # Handle case where create_redis_pool might return None on failure (if modified)
             raise ConnectionError("create_redis_pool returned None")
    except Exception as e: # Catch any exception during Redis setup
        logger.error(f"Redis setup failed: {e}", exc_info=True)
        setattr(app.state, 'redis_pool', None)
        setattr(app.state, 'redis', None)
        app.state.limiter = limiter
        logger.warning("Rate limiter continuing with in memory storage.")
    # --- Connect Database ---
    # Load DB config here from environment variables
    db_user_main = os.getenv("POSTGRES_USER", "user")
    db_password_main = os.getenv("POSTGRES_PASSWORD", "password") # Ensure PW is read
    db_name_main = os.getenv("POSTGRES_DB", "whatbeatsrock_db")
    # Use 127.0.0.1 as default now that we know localhost caused issues
    db_host_main = os.getenv("POSTGRES_HOST", "127.0.0.1")
    db_port_main = int(os.getenv("POSTGRES_PORT", 5432))
    logger.info(f"DB Config loaded in main: Host={db_host_main}, Port={db_port_main}, User={db_user_main}, DB={db_name_main}")

    db_pool_instance = None
    try:
        logger.info("Attempting DB connection call...")
        # Pass loaded config explicitly to connect_db (expecting modified connect_db)
        db_pool_instance = await connect_db(
            db_user=db_user_main,
            db_password=db_password_main,
            db_name=db_name_main,
            db_host=db_host_main,
            db_port=db_port_main
        )
        # connect_db now sets the global DB_POOL used by other db functions
        setattr(app.state, 'db_pool', db_pool_instance) # Also store on app state if needed elsewhere directly
        logger.info("DB pool should be created and attached to app state.")
    except Exception as e:
        logger.error(f"Database setup failed in main: {e}", exc_info=True)
        setattr(app.state, 'db_pool', None) # Ensure state reflects failure

    logger.info("--- Startup complete ---")
    # === End of Startup Logic ===

    yield # <<<--- SINGLE YIELD

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
app.state.limiter = limiter # Attach the initial (memory) limiter to state
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) # Add handler

# --- Include Routers ---
app.include_router(game_routes.router)

# --- Root Endpoint ---
'''
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
'''
@app.get("/", response_class=FileResponse,include_in_schema=False)
async def read_index():
    # Ensure this path is correct relative to where you run uvicorn
    # If you run uvicorn from the project root, this should work
    return "frontend/templates/index.html"

# --- Mount Static Files Directory ---
# This serves files like styles.css, app.js from the frontend directory
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


# --- Direct Run Block (for testing) ---
if __name__ == "__main__":
    import uvicorn
    logger.warning("Running directly with __main__, use 'uvicorn backend.main:app' for production/proper lifespan.")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True) # Use string format for reload

# logger.info("FastAPI app instance defined (module loaded).") # This might log too early