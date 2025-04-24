# backend/api/game_routes.py
from fastapi import APIRouter, HTTPException, status, Body, Depends, Request
from pydantic import BaseModel, Field
import logging
import uuid
from typing import List
import asyncio

# --- Rate Limiting Imports ---
from ..core.limiter import limiter
from slowapi.util import get_remote_address # Import ONLY the key function
# --- End Rate Limiting Imports ---

# --- Core Logic Imports ---
from ..core.cache import get_redis_connection
from ..core.ai_client import generate_ai_verdict
import redis.asyncio as redis
from ..core.db_client import increment_global_guess_count
from ..core.moderation import is_guess_clean
# --- End Core Logic Imports ---
from enum import Enum 
from fastapi import Query  
# --- Setup ---
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/game", tags=["Game Logic"])
key_func = get_remote_address # Define key func for limiter decorator
# --- End Setup ---

# --- Constants ---
INITIAL_WORD = "Rock"
SESSION_KEY_PREFIX = "session:"
SESSION_GUESSES_SUFFIX = ":guesses"
SESSION_SCORE_SUFFIX = ":score"
SESSION_TTL_SECONDS = 3600
RATE_LIMIT_GUESS = "15/minute"
RATE_LIMIT_HISTORY = "30/minute"
# --- End Constants ---
class Persona(str, Enum):
    SERIOUS = "serious"
    CHEERY = "cheery"
# --- Pydantic Models ---
class GuessInput(BaseModel):
    current_word: str = Field(..., examples=[INITIAL_WORD, "Paper"])
    user_guess: str = Field(..., min_length=1, examples=["Paper", "Scissors"])
    session_id: str | None = Field(None, description="The unique ID for the current game session.")

class GuessResponse(BaseModel):
    message: str
    next_word: str | None = None
    score: int = 0
    game_over: bool = False
    global_count: int | None = None
    session_id: str | None = None

class GameHistory(BaseModel):
    session_id: str
    guesses: List[str]
    score: int
# --- End Pydantic Models ---


# --- Dependencies ---
async def get_redis(request: Request) -> redis.Redis:
    redis_conn = getattr(request.app.state, 'redis', None)
    if not redis_conn:
        logger.error("Redis connection not available in app state!")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis service not available.")
    return redis_conn

# REMOVED get_limiter and rate limiting dependency functions
# --- End Dependencies ---


# --- Game Logic Helpers (Redis Interactions) ---
async def check_duplicate_guess(redis_conn: redis.Redis, session_id: str, guess: str) -> bool:
    session_list_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_GUESSES_SUFFIX}"
    guesses = await redis_conn.lrange(session_list_key, 0, -1)
    logger.debug(f"Session {session_id} existing guesses: {guesses}")
    return guess.lower() in [g.lower() for g in guesses]

async def add_guess_to_session(redis_conn: redis.Redis, session_id: str, word: str):
    session_list_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_GUESSES_SUFFIX}"
    await redis_conn.rpush(session_list_key, word)
    await redis_conn.expire(session_list_key, SESSION_TTL_SECONDS)
    logger.info(f"Added '{word}' to session {session_id}. List key: {session_list_key}")

async def increment_session_score(redis_conn: redis.Redis, session_id: str) -> int:
    session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}"
    new_score = await redis_conn.incr(session_score_key)
    await redis_conn.expire(session_score_key, SESSION_TTL_SECONDS)
    logger.info(f"Incremented score for session {session_id} to {new_score}. Score key: {session_score_key}")
    return new_score

async def get_session_score(redis_conn: redis.Redis, session_id: str) -> int:
    session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}"
    score = await redis_conn.get(session_score_key)
    return int(score) if score else 0

async def get_session_history(redis_conn: redis.Redis, session_id: str) -> List[str]:
     session_list_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_GUESSES_SUFFIX}"
     guesses = await redis_conn.lrange(session_list_key, 0, -1)
     return guesses
# --- Persona-based Message generation helpers ---
def generate_success_message(persona:Persona, guess:str , current:str, count: int | None, session_id:str, is_new: bool) -> str:
    base = f" '{guess}' beats '{current}'."
    if count is not None:
        base+= f"Global count for '{guess}':{count}."
    if is_new:
        base+= f"Your session ID is {session_id}."
    if persona == Persona.CHEERY:
        return f"Wowzers! 👏 {base} Good Stuff!"
    return f"Affirmative. {base}"
def generate_ai_fail_message(persona: Persona, guess: str, current: str, is_start: bool) -> str:
    fail_base = f"AI thinks '{guess}' doesn't beat '{current}'."
    if persona == Persona.CHEERY:
        if is_start:
            return f"Aw, man! 🥺 {fail_base} Game hasn't started. Try beating '{INITIAL_WORD}'!"
        else:
            return f"Oops! 🤭 {fail_base} Keep trying with '{current}'!"
    # Default to SERIOUS
    if is_start:
         return f"Negative. {fail_base} Game not initiated. Attempt validation against '{INITIAL_WORD}'."
    else:
         return f"Negative. {fail_base} Maintain current word '{current}'."


def generate_duplicate_message(persona: Persona, guess: str, score: int) -> str:
    if persona == Persona.CHEERY:
        return f"Yikes! 😅 You already used '{guess}'. Game over! Your  score was {score}!"
    # Default to SERIOUS
    return f"Duplicate entry: '{guess}'. Game terminated. Final score: {score}."

# --- Core Game Endpoint ---
# USE DECORATOR DIRECTLY ON ROUTE
@router.post("/guess", response_model=GuessResponse)
@limiter.limit(RATE_LIMIT_GUESS, key_func=key_func) # Apply decorator
async def submit_guess(
    
    request: Request, # Request param IS needed for key_func
    persona: Persona = Query(Persona.SERIOUS, description="Select the host's persona(serious or cheery)"),
    guess_input: GuessInput = Body(...),
    redis_conn: redis.Redis = Depends(get_redis)
):
    """Handles a user's guess, validates it, checks duplicates, asks AI, updates state. Rate limited."""
    # Rate limiting check is handled by the decorator

    logger.info(f"Received guess: {guess_input.user_guess} vs {guess_input.current_word} (Session: {guess_input.session_id})")

    # --- Input Processing ---
    session_id_from_input = guess_input.session_id
    user_guess = guess_input.user_guess.strip()
    current_word = guess_input.current_word.strip()
    is_new_session = False
    session_id_active = session_id_from_input

    if not user_guess:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Guess cannot be empty.")
    #-- moderation check --
    if not is_guess_clean(user_guess):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Inappropriate language detected in guess. Please keep it clean!")
    #--- End Moderation check ---
    logger.info(f"Received guess (clean) : {user_guess} vs {current_word} (Session: {session_id_active}, Persona: {persona.value})")
    # --- Session Handling & Validation ---
    if session_id_active:
        session_score_key = f"{SESSION_KEY_PREFIX}{session_id_active}{SESSION_SCORE_SUFFIX}"
        if not await redis_conn.exists(session_score_key):
            logger.warning(f"Session ID '{session_id_active}' provided but not found in Redis (key: {session_score_key}).")
            if current_word.lower() != INITIAL_WORD.lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired session ID.")
            else:
                logger.info(f"Allowing restart with Rock for potentially invalid session ID {session_id_active}.")
                session_id_active = None
                is_new_session = True
        else: # Session exists
            session_guesses = await get_session_history(redis_conn, session_id_active)
            if session_guesses and session_guesses[-1].lower() != current_word.lower():
                logger.warning(f"Mismatch: Client sent current_word='{current_word}', but last word in session {session_id_active} was '{session_guesses[-1]}'")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Current word mismatch. Expected '{session_guesses[-1]}'."
                )
    elif current_word.lower() != INITIAL_WORD.lower():
        logger.warning(f"Attempt to guess against '{current_word}' without a session ID.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Must provide a valid session_id or guess against '{INITIAL_WORD}' to start."
        )
    else: # No session ID and current word is Rock
        is_new_session = True
        session_id_active = None

    # --- Duplicate Check ---
    if session_id_active and not is_new_session:
        is_duplicate = await check_duplicate_guess(redis_conn, session_id_active, user_guess)
        if is_duplicate:
            logger.info(f"Duplicate guess '{user_guess}' in session {session_id_active}. Game Over.")
            score = await get_session_score(redis_conn, session_id_active)
            message = generate_duplicate_message(persona,user_guess,score)
            return GuessResponse(
                message=message, 
                score=score, game_over=True, session_id=session_id_active
            )

    # --- AI Validation ---
    ai_says_yes: bool = False
    try:
        ai_says_yes = await asyncio.wait_for(
            generate_ai_verdict(current_word, user_guess, redis_conn),
            timeout=20.0
        )
    except asyncio.TimeoutError:
         logger.error(f"AI call timed out for '{user_guess}' vs '{current_word}'.")
         ai_says_yes = False
    except Exception as e:
        logger.error(f"Unexpected error during AI verdict generation: {e}", exc_info=True)
        ai_says_yes = False

    # --- Process Result ---
    if ai_says_yes:
        # --- Success Path ---
        if is_new_session or not session_id_active:
            session_id_active = str(uuid.uuid4())
            is_new_session = True
            logger.info(f"Starting new session: {session_id_active}")
        #    await add_guess_to_session(redis_conn, session_id_active, INITIAL_WORD)

        await add_guess_to_session(redis_conn, session_id_active, user_guess)
        current_score = await increment_session_score(redis_conn, session_id_active)
        global_count = await increment_global_guess_count(user_guess)

        message = generate_success_message(persona,user_guess,current_word,global_count,session_id_active,is_new_session)
        return GuessResponse(
            message=message, next_word=user_guess, score=current_score,
            game_over=False, session_id=session_id_active, global_count=global_count
        )
    else:
        # --- Failure Path ---
        score = await get_session_score(redis_conn, session_id_active) if session_id_active else 0
        next_word_on_fail = current_word
        is_start_of_game = not session_id_active
        if is_start_of_game:
            next_word_on_fail = INITIAL_WORD
        message = generate_ai_fail_message(persona,user_guess,current_word,is_start_of_game)
        return GuessResponse(
            message=message, next_word=next_word_on_fail, score=score,
            game_over=False, session_id=session_id_active
        )


# --- History Endpoint ---
# USE DECORATOR DIRECTLY ON ROUTE
@router.get("/{session_id}/history", response_model=GameHistory)
@limiter.limit(RATE_LIMIT_HISTORY, key_func=key_func) # Apply decorator
async def get_game_history(
    request: Request, # Request param IS needed for key_func
    session_id: str,
    redis_conn: redis.Redis = Depends(get_redis)
):
     """Retrieves the guess history and score for a given session. Rate limited."""
     # Rate limiting check is handled by the decorator

     logger.info(f"Fetching history for session: {session_id}")
     session_score_key = f"{SESSION_KEY_PREFIX}{session_id}{SESSION_SCORE_SUFFIX}"
     if not await redis_conn.exists(session_score_key):
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
     guesses = await get_session_history(redis_conn, session_id)
     score = await get_session_score(redis_conn, session_id)
     return GameHistory(session_id=session_id, guesses=guesses, score=score)