# backend/api/game_routes.py
from fastapi import APIRouter, HTTPException, status, Body, Depends, Request
from pydantic import BaseModel, Field
import logging
import uuid # for generating session IDs
from typing import List  # for history response
import asyncio

# Importing Redis connection and AI client functions
from ..core.cache import get_redis_connection
from ..core.ai_client import generate_ai_verdict
import redis.asyncio as redis
from ..core.db_client import increment_global_guess_count
# Get a logger for this module
logger = logging.getLogger(__name__)

# Create an API router for game-related endpoints
router = APIRouter(
    prefix="/game", # All routes in this file will start with /game
    tags=["Game Logic"] # Tag for grouping in API docs
)

# --- Constants ---
INITIAL_WORD = "Rock"
SESSION_KEY_PREFIX = "session:"
SESSION_GUESSES_SUFFIX = ":guesses"
SESSION_SCORE_SUFFIX = ":score"
SESSION_TTL_SECONDS = 3600 # Expire sessions after 1 hour of inactivity

# --- Pydantic Models ---
class GuessInput(BaseModel):
    """Defines the expected JSON body for the guess endpoint."""
    current_word: str = Field(
        ...,
        description="The word the user is trying to beat (e.g., 'Rock').",
        examples=[INITIAL_WORD, "Paper"]
    )
    user_guess: str = Field(
        ...,
        description="The word the user proposes beats the current_word.",
        min_length=1,
        examples=["Paper", "Scissors"]
    )
    session_id: str | None = Field(None, description="The unique ID for the current game session.")

class GuessResponse(BaseModel):
    """Defines the structure of the response after a guess."""
    message: str
    next_word: str | None = None
    score: int = 0
    game_over: bool = False
    global_count: int | None = None # Placeholder for DB integration
    session_id: str | None = None

class GameHistory(BaseModel):
    """Defines the structure for the game history response."""
    session_id: str
    guesses: List[str]
    score: int

# --- Dependency for Redis ---
async def get_redis(request: Request) -> redis.Redis:
    """Dependency to get the Redis connection from app state."""
    if not request.app.state.redis:
        logger.error("Redis connection not available in app state!")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot connect to Redis service."
        )
    return request.app.state.redis

# --- Game Logic Helpers (Redis Interactions) ---

async def check_duplicate_guess(redis_conn: redis.Redis, session_id: str, guess: str) -> bool:
    """Checks if a guess already exists in the session's list in Redis."""
    session_list_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_GUESSES_SUFFIX}"
    guesses = await redis_conn.lrange(session_list_key, 0, -1)
    logger.debug(f"Session {session_id} existing guesses: {guesses}")
    return guess.lower() in [g.lower() for g in guesses] # Case-insensitive duplicate check

async def add_guess_to_session(redis_conn: redis.Redis, session_id: str, word: str):
    """Adds a word to the session's list and resets TTL."""
    session_list_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_GUESSES_SUFFIX}"
    await redis_conn.rpush(session_list_key, word)
    await redis_conn.expire(session_list_key, SESSION_TTL_SECONDS)
    logger.info(f"Added '{word}' to session {session_id}. List key: {session_list_key}")

async def increment_session_score(redis_conn: redis.Redis, session_id: str) -> int:
    """Increments the session score in Redis and resets TTL."""
    session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}"
    new_score = await redis_conn.incr(session_score_key)
    # Also reset TTL for score key on activity
    await redis_conn.expire(session_score_key, SESSION_TTL_SECONDS)
    logger.info(f"Incremented score for session {session_id} to {new_score}. Score key: {session_score_key}")
    return new_score

async def get_session_score(redis_conn: redis.Redis, session_id: str) -> int:
    """Gets the session score from Redis."""
    session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}"
    score = await redis_conn.get(session_score_key)
    return int(score) if score else 0

async def get_session_history(redis_conn: redis.Redis, session_id: str) -> List[str]:
     """Gets the list of guesses for the session."""
     session_list_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_GUESSES_SUFFIX}"
     guesses = await redis_conn.lrange(session_list_key, 0, -1)
     return guesses

# --- Core Game Endpoint ---
@router.post("/guess", response_model=GuessResponse)
async def submit_guess(
    request: Request,
    guess_input: GuessInput = Body(...),
    redis_conn: redis.Redis = Depends(get_redis)
):
    """Handles a user's guess, validates it, checks duplicates, asks AI, and updates state."""
    logger.info(f"Received guess: {guess_input.user_guess} vs {guess_input.current_word} (Session: {guess_input.session_id})")

    session_id = guess_input.session_id
    # Normalize inputs slightly (e.g., strip whitespace)
    user_guess = guess_input.user_guess.strip()
    current_word = guess_input.current_word.strip()
    is_new_session = False

    if not user_guess: # Reject empty guesses after stripping
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Guess cannot be empty."
        )

    # --- Session Handling & Basic Validation ---
    if session_id:
        session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}"
        # Check if session key exists. If not, treat as potentially expired/invalid.
        if not await redis_conn.exists(session_score_key):
             logger.warning(f"Session ID '{session_id}' provided but not found in Redis (key: {session_score_key}).")
             # Allow starting over implicitly only if the client tries to beat "Rock"
             if current_word.lower() != INITIAL_WORD.lower():
                  raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired session ID.")
             else:
                  logger.info(f"Allowing restart with Rock for potentially invalid session ID {session_id}.")
                  session_id = None # Force start of a new session

        # Verify current_word if session exists and has guesses
        if session_id: # Re-check as it might have been reset
            session_guesses = await get_session_history(redis_conn, session_id)
            # Ensure comparison is case-insensitive if needed, or keep it strict
            if session_guesses and session_guesses[-1].lower() != current_word.lower():
                 logger.warning(f"Mismatch: Client sent current_word='{current_word}', but last word in session {session_id} was '{session_guesses[-1]}'")
                 raise HTTPException(
                     status_code=status.HTTP_409_CONFLICT,
                     detail=f"Current word mismatch. Expected '{session_guesses[-1]}'."
                 )
    elif current_word.lower() != INITIAL_WORD.lower():
        # No session ID, but trying to guess against something other than Rock
        logger.warning(f"Attempt to guess against '{current_word}' without a session ID.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Must provide a valid session_id to guess against words other than '{INITIAL_WORD}'."
        )

    # --- Duplicate Check (only if session exists, case-insensitive) ---
    if session_id:
        is_duplicate = await check_duplicate_guess(redis_conn, session_id, user_guess)
        if is_duplicate:
            logger.info(f"Duplicate guess '{user_guess}' in session {session_id}. Game Over.")
            score = await get_session_score(redis_conn, session_id)
            return GuessResponse(
                message=f"Game Over! You already used '{user_guess}'. Final score: {score}",
                score=score,
                game_over=True,
                session_id=session_id
            )

    # --- AI Validation ---
    ai_says_yes: bool = False  # Initialize variable before try block

    try:
        # Call the imported function from ai_client.py
        ai_says_yes = await asyncio.wait_for(
            generate_ai_verdict(current_word, user_guess),
            timeout=20.0 # Increased timeout slightly
        )
    except asyncio.TimeoutError:
         logger.error(f"AI call timed out for '{user_guess}' vs '{current_word}'.")
         ai_says_yes = False # Default to False on timeout
    except Exception as e:
        logger.error(f"Unexpected error during AI verdict generation: {e}", exc_info=True)
        ai_says_yes = False # Default to False on other errors

    # --- Process Result ---
    if ai_says_yes:
        # --- Success Path ---
        if not session_id:
            # Start a new session
            session_id = str(uuid.uuid4())
            is_new_session = True
            logger.info(f"Starting new session: {session_id}")
            await add_guess_to_session(redis_conn, session_id, INITIAL_WORD) # Add Rock first

        # Add the successful guess and update score
        await add_guess_to_session(redis_conn, session_id, user_guess)
        current_score = await increment_session_score(redis_conn, session_id)

         #Increment global counter in DB 
        global_count = await increment_global_guess_count(user_guess)
        message = f"Nice! '{user_guess}' beats '{current_word}'."
        #global count to message if available
        if global_count is not None:
            message+= f"Global count for '{user_guess}:{global_count}."
        # Append session ID message only if it's a truly new session start
        if is_new_session:
            message += f" Your session ID is {session_id}."

        return GuessResponse(
            message=message,
            next_word=user_guess,
            score=current_score,
            game_over=False,
            session_id=session_id,
            global_count=global_count
            # global_count will be added later
        )
    else:
        # --- Failure Path (AI said NO or Error occurred) ---
        score = await get_session_score(redis_conn, session_id) if session_id else 0
        next_word_on_fail = current_word # Default: word to beat stays the same

        if not session_id: # Failed on the very first guess
             message = f"AI thinks '{user_guess}' doesn't beat '{current_word}'. Game hasn't started. Try beating '{INITIAL_WORD}'."
             next_word_on_fail = INITIAL_WORD # Reset back to Rock
        else: # Failed mid-game
             message = f"AI thinks '{user_guess}' doesn't beat '{current_word}'. Keep trying with '{current_word}'!"
             # next_word_on_fail is already current_word

        return GuessResponse(
            message=message,
            next_word=next_word_on_fail,
            score=score,
            game_over=False, # Game doesn't end on wrong AI validation
            session_id=session_id
        )

# --- History Endpoint ---
@router.get("/{session_id}/history", response_model=GameHistory)
async def get_game_history(
    session_id: str,
    redis_conn: redis.Redis = Depends(get_redis)
):
    """Retrieves the guess history and score for a given session."""
    logger.info(f"Fetching history for session: {session_id}")
    session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}" # Use score key existence check

    # Check if session exists using EXISTS on the score key is sufficient
    if not await redis_conn.exists(session_score_key):
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    guesses = await get_session_history(redis_conn, session_id)
    score = await get_session_score(redis_conn, session_id)

    return GameHistory(session_id=session_id, guesses=guesses, score=score)