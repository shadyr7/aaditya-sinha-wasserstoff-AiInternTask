# backend/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging

# Import the router from the api module
from .api import game_routes # Use relative import

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    yield
    logger.info("Application shutting down...")

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
    return {
        "message": "Welcome to the 'What Beats Rock?' GenAI Game API!",
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Running directly with Uvicorn for development testing.")
    uvicorn.run(app, host="127.0.0.1", port=8000)

logger.info("FastAPI app instance defined.")