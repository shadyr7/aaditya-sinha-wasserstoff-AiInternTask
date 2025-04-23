# backend/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging

# Import the router from the api module
from .api import game_routes # Use relative import
from.core.cache import create_redis_pool, close_redis_pool, get_redis_connection
# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    #Creating Redis connection pool on startup
    try:
        app.state.redis_pool = await create_redis_pool()
        app.state.redis = get_redis_connection()
        logger.info("Redis pool created and attached to app state.")
    except ConnectionError as e:
        logger.error(f"Couldnt establish Redis connection: {e}. App might not function correctly.")
        app.state.redis_pool = None 
        app.state.redis = None
    yield # The app runs here

    logger.info("Application shutting down...")
    await close_redis_pool()
    logger.info("Redis pool closed.")

app = FastAPI(
    title="GenAI 'What Beats Rock' Game",
    description="""
    An interactive guessing game powered by Generative AI.
    Submit guesses to beat the current word and build a chain.
    Watch out for duplicates!
    """,
    version="0.1.0",
    lifespan=lifespan
)

# --- Include Routers ---
app.include_router(game_routes.router) # Add the game routes here!

@app.get("/")
async def read_root():
    logger.info("Root endpoint accessed.")
    # to check if redis is available from app state
    redis_available = app.state.redis is not None
    return {
        "message": "Welcome to the 'What Beats Rock?' GenAI Game API!",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "redis_connected": redis_available
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Running directly with Uvicorn for development testing.")
    uvicorn.run(app, host="127.0.0.1", port=8000)

logger.info("FastAPI app instance defined.")