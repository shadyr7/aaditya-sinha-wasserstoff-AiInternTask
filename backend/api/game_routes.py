# backend/api/game_routes.py
from fastapi import APIRouter, HTTPException, status, Body, Depends, Request # Added Body added request and depends
from pydantic import BaseModel, Field
import logging
import uuid # for generating session IDs
from typing import List  # for history response
#importing the redis connection getter
from ..core.cache import get_redis_connection 
from ..core.ai_client import generate_ai_verdict
import asyncio 
import redis.asyncio as redis 
# Get a logger for this module
logger = logging.getLogger(__name__)

# Create an API router for game-related endpoints
router = APIRouter(
    prefix="/game", # All routes in this file will start with /game
    tags=["Game Logic"] # Tag for grouping in API docs
)
INITIAL_WORD = "Rock"
SESSION_KEY_PREFIX = "session:"
SESSION_GUESSES_SUFFIX = ":guesses"
SESSION_SCORE_SUFFIX = ":score"
SESSION_TTL_SECONDS = 3600

# --- Pydantic Model for Guess Input ---
class GuessInput(BaseModel):
    """Defines the expected JSON body for the guess endpoint."""
    current_word: str = Field(
        ..., # Ellipsis means this field is required
        description="The word the user is trying to beat (e.g., 'Rock').",
        examples=[INITIAL_WORD, "Paper"]
    )
    user_guess: str = Field(
        ...,
        description="The word the user proposes beats the current_word.",
        min_length=1, # Basic validation: guess cannot be empty
        examples=["Paper", "Scissors"]
    )
    # Optional: Add session_id later if needed for state management
    # session_id: str | None = None
    session_id: str | None = Field(None,description="The unique ID for the current game session.")
# --- Pydantic Model for Guess Output (Example Structure) ---
# We'll refine this later based on actual game logic results
class GuessResponse(BaseModel):
    """Defines the structure of the response after a guess."""
    message: str
    next_word: str | None = None # The new word if the guess was successful
    score: int = 0
    game_over: bool = False
    global_count: int | None = None # How many times the guess was made globally
    session_id: str | None = None 
class GameHistory(BaseModel):
    session_id: str
    guesses: List[str]
    score: int

# --- Dependency for Redis ---
# This makes getting the Redis connection cleaner in route functions
# It relies on the pool being initialized in the lifespan manager
async def get_redis(request: Request) -> redis.Redis:
    """Dependency to get the Redis connection from app state."""
    if not request.app.state.redis:
        # This should ideally be caught by readiness probes in production
        logger.error("Redis connection not available in app state!")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot connect to Redis service."
        )
    return request.app.state.redis

# --- Game Logic Helpers (can be moved to core/game_logic.py later) ---

async def check_duplicate_guess(redis_conn: redis.Redis, session_id: str, guess: str) -> bool:
    """Checks if a guess already exists in the session's list in Redis."""
    session_list_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_GUESSES_SUFFIX}"
    # LPOS is efficient for checking existence in Redis >= 6.0.6
    # Alternatively, LRANGE 0 -1 and check in Python
    # For simplicity & compatibility, let's use LRANGE
    guesses = await redis_conn.lrange(session_list_key, 0, -1)
    logger.debug(f"Session {session_id} existing guesses: {guesses}")
    return guess in guesses

async def add_guess_to_session(redis_conn: redis.Redis, session_id: str, word: str):
    """Adds a word to the session's list and resets TTL."""
    session_list_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_GUESSES_SUFFIX}"
    await redis_conn.rpush(session_list_key, word)
    await redis_conn.expire(session_list_key, SESSION_TTL_SECONDS) # Reset TTL on activity
    logger.info(f"Added '{word}' to session {session_id}. List key: {session_list_key}")

async def increment_session_score(redis_conn: redis.Redis, session_id: str) -> int:
    """Increments the session score in Redis and resets TTL."""
    session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}"
    # Use INCR for atomic increment, returns the new value
    new_score = await redis_conn.incr(session_score_key)
    await redis_conn.expire(session_score_key, SESSION_TTL_SECONDS) # Reset TTL
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

# --- AI Client Placeholder ---
    
    # ----------------------------------------------------

# --- Updated Guess Endpoint ---
@router.post("/guess", response_model=GuessResponse)
async def submit_guess(
    request: Request, # Inject the request object to access app state via dependency
    guess_input: GuessInput = Body(...),
    redis_conn: redis.Redis = Depends(get_redis) # Use dependency injection for Redis
):
    logger.info(f"Received guess: {guess_input.user_guess} vs {guess_input.current_word} (Session: {guess_input.session_id})")

    session_id = guess_input.session_id
    user_guess = guess_input.user_guess
    current_word = guess_input.current_word
    is_new_session = False

    # --- Session Handling & Basic Validation ---
    if session_id:
        # Check if session exists (e.g., by checking if the score key exists)
        session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}"
        if not await redis_conn.exists(session_score_key):
             logger.warning(f"Session ID '{session_id}' provided but not found in Redis.")
             # Optional: Treat as expired or invalid session? Or allow restart?
             # For now, let's reject it if it doesn't exist after first round.
             if current_word != INITIAL_WORD: # Allow starting over implicitly if client lost state
                  raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired session ID.")
             else: # Allow restarting with "Rock" even if ID is technically invalid
                  logger.info(f"Allowing restart with Rock for potentially invalid session ID {session_id}.")
                  session_id = None # Treat as new session start


        # Verify the `current_word` matches the last word in the session's history
        # This prevents API misuse where client sends wrong `current_word`
        session_guesses = await get_session_history(redis_conn, session_id) if session_id else []
        if session_guesses and session_guesses[-1] != current_word:
             logger.warning(f"Mismatch: Client sent current_word='{current_word}', but last word in session {session_id} was '{session_guesses[-1]}'")
             raise HTTPException(
                 status_code=status.HTTP_409_CONFLICT,
                 detail=f"Current word mismatch. Expected '{session_guesses[-1]}'."
             )
    elif current_word != INITIAL_WORD:
        # If no session ID is provided, the game MUST start with the initial word
        logger.warning(f"Attempt to guess against '{current_word}' without a session ID.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Must provide a valid session_id to guess against words other than '{INITIAL_WORD}'."
        )

    # --- Duplicate Check ---
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

    # --- AI Validation (Placeholder) ---
            # --- AI Validation (REAL CALL) ---
        # Replace the placeholder call with the real one
        try:
            # Call the imported function from ai_client.py
            ai_says_yes = await asyncio.wait_for(
                generate_ai_verdict(current_word, user_guess),
                timeout=15.0 # Example: 15 second timeout per attempt
            )
        except asyncio.TimeoutError:
             logger.error(f"AI call timed out for '{user_guess}' vs '{current_word}'.")
             ai_says_yes = False # Treat timeout as NO
        except Exception as e:
            # Catch any unexpected errors from the AI call not handled by tenacity's retry
            # or other potential issues during the call.
            logger.error(f"Unexpected error during AI verdict generation: {e}", exc_info=True)
            ai_says_yes = False # Treat errors as NO

        # --- Process Result ---
        # The 'if ai_says_yes:' block below this uses the result

    # --- Process Result ---
    if ai_says_yes:
        if not session_id:
            # Start a new session
            session_id = str(uuid.uuid4()) # Generate a unique ID
            is_new_session = True
            logger.info(f"Starting new session: {session_id}")
            # Add the *initial* word to the list only when starting
            await add_guess_to_session(redis_conn, session_id, INITIAL_WORD)

        # Add the successful guess
        await add_guess_to_session(redis_conn, session_id, user_guess)
        # Increment score
        current_score = await increment_session_score(redis_conn, session_id)
        # TODO: Increment global counter in DB later

        message = f"Nice! '{user_guess}' beats '{current_word}'."
        if is_new_session:
            message += f" Your session ID is {session_id}."

        return GuessResponse(
            message=message,
            next_word=user_guess,
            score=current_score,
            game_over=False,
            session_id=session_id
            # global_count = fetch from DB later
        )
    else:
        # AI said NO
        score = await get_session_score(redis_conn, session_id) if session_id else 0
        message = f"Nope! AI thinks '{user_guess}' doesn't beat '{current_word}'. Try again!"
        if not session_id: # If first guess failed
             message = f"Nope! AI thinks '{user_guess}' doesn't beat '{current_word}'. Game hasn't started."
             current_word = INITIAL_WORD # Reset back to Rock
        else: # If guess failed mid-game
             message = f"Nope! AI thinks '{user_guess}' doesn't beat '{current_word}'. Keep trying with '{current_word}'!"
             # current_word remains the same


        return GuessResponse(
            message=message,
            next_word=current_word, # The word to beat remains the same
            score=score,
            game_over=False, # Game doesn't end on wrong guess
            session_id=session_id
        )


# --- Add History Endpoint ---
@router.get("/{session_id}/history", response_model=GameHistory)
async def get_game_history(
    session_id: str,
    redis_conn: redis.Redis = Depends(get_redis)
):
    """Retrieves the guess history and score for a given session."""
    logger.info(f"Fetching history for session: {session_id}")
    session_list_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_GUESSES_SUFFIX}"
    session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}"

    # Check if session exists using EXISTS on one of the keys
    if not await redis_conn.exists(session_score_key):
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    guesses = await get_session_history(redis_conn, session_id)
    score = await get_session_score(redis_conn, session_id)

    return GameHistory(session_id=session_id, guesses=guesses, score=score)

