# backend/api/game_routes.py
from fastapi import APIRouter, HTTPException, status, Body # Added Body
from pydantic import BaseModel, Field
import logging

# Get a logger for this module
logger = logging.getLogger(__name__)

# Create an API router for game-related endpoints
router = APIRouter(
    prefix="/game", # All routes in this file will start with /game
    tags=["Game Logic"] # Tag for grouping in API docs
)

# --- Pydantic Model for Guess Input ---
class GuessInput(BaseModel):
    """Defines the expected JSON body for the guess endpoint."""
    current_word: str = Field(
        ..., # Ellipsis means this field is required
        description="The word the user is trying to beat (e.g., 'Rock').",
        examples=["Rock", "Paper"]
    )
    user_guess: str = Field(
        ...,
        description="The word the user proposes beats the current_word.",
        min_length=1, # Basic validation: guess cannot be empty
        examples=["Paper", "Scissors"]
    )
    # Optional: Add session_id later if needed for state management
    # session_id: str | None = None

# --- Pydantic Model for Guess Output (Example Structure) ---
# We'll refine this later based on actual game logic results
class GuessResponse(BaseModel):
    """Defines the structure of the response after a guess."""
    message: str
    next_word: str | None = None # The new word if the guess was successful
    score: int | None = None
    game_over: bool = False
    global_count: int | None = None # How many times the guess was made globally

# --- Define the Guess Endpoint ---
@router.post("/guess", response_model=GuessResponse) # Specify the output model
async def submit_guess(
    guess_input: GuessInput = Body(...) # Expect the input model in the request body
):
    """
    Submits a user's guess to beat the current word.
    Validates the input and (eventually) checks against AI and game rules.
    """
    logger.info(f"Received guess: User wants '{guess_input.user_guess}' to beat '{guess_input.current_word}'.")

    # --- Placeholder Logic (To be replaced later) ---
    # TODO:
    # 1. Check for profanity in guess_input.user_guess
    # 2. Check if user_guess is already in the current session's list (Game Over?)
    # 3. Call AI to validate if user_guess beats current_word
    # 4. If YES:
    #    - Add user_guess to session list
    #    - Increment score
    #    - Increment global counter for user_guess in DB
    #    - Prepare success response
    # 5. If NO:
    #    - Prepare failure response
    # 6. Handle Game Over state

    # For now, just return a basic placeholder response based on input
    # This simulates a successful guess for testing the endpoint structure
    placeholder_message = f"Received: '{guess_input.user_guess}' vs '{guess_input.current_word}'. Processing..."
    placeholder_next_word = guess_input.user_guess # Assume success for now
    placeholder_score = 1 # Dummy score
    placeholder_global_count = 0 # Dummy count

    logger.info("Placeholder logic: Returning simulated success.")

    return GuessResponse(
        message=placeholder_message,
        next_word=placeholder_next_word,
        score=placeholder_score,
        game_over=False, # Assume not game over for now
        global_count=placeholder_global_count
    )

# You can add other game-related routes here later (e.g., /history, /start)