# backend/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- App Lifespan Management (Optional but good practice) ---
# This is where you might initialize resources like DB connections
# or AI clients if needed globally when the app starts, and clean
# them up when it stops. We'll add more here later.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    logger.info("Application starting up...")
    # Example: Initialize DB pool, load ML models, etc.
    # await connect_to_db()
    # await load_ml_model()
    yield # The application runs while yielded
    # Code to run on shutdown
    logger.info("Application shutting down...")
    # Example: Close DB connections, release resources
    # await close_db_connection()

# --- Create the FastAPI App Instance ---
app = FastAPI(
    title="GenAI 'What Beats Rock' Game",
    description="""
    An interactive guessing game powered by Generative AI.
    Submit guesses to beat the current word and build a chain.
    Watch out for duplicates!
    """,
    version="0.1.0",
    lifespan=lifespan # Use the lifespan manager
)

# --- Root Endpoint ---
@app.get("/")
async def read_root():
    """
    Root endpoint providing a welcome message and basic API info.
    """
    logger.info("Root endpoint accessed.")
    return {
        "message": "Welcome to the 'What Beats Rock?' GenAI Game API!",
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }

# --- Placeholder for Game Routes ---
# We will add game-specific endpoints (like /game/guess) later
# using API Routers for better organization.

# --- Run with Uvicorn (if run directly, mainly for quick local checks) ---
# The standard way to run will be using the uvicorn command from the terminal
if __name__ == "__main__":
    import uvicorn
    logger.info("Running directly with Uvicorn for development testing.")
    # Note: --reload is better handled via the command line `uvicorn backend.main:app --reload`
    uvicorn.run(app, host="127.0.0.1", port=8000)

logger.info("FastAPI app instance defined.")