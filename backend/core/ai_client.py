# backend/core/ai_client.py
import os
import logging
from dotenv import load_dotenv
import openai # Or import google.generativeai as genai, etc.
import asyncio
from tenacity import retry, stop_after_attempt, wait_random_exponential

logger = logging.getLogger(__name__)
load_dotenv()

# --- Configure AI Client ---
# Example using OpenAI - adapt for other providers
# Make sure OPENAI_API_KEY is set in your .env file
openai_client = None
try:
    # It's better practice to initialize the client once
    # potentially in the app lifespan or lazily on first use.
    # For simplicity here, we initialize when the module loads.
    # Ensure API key is loaded before this line executes.
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not found in environment variables.")
        # raise ValueError("OPENAI_API_KEY environment variable not set.") # Be stricter if needed
    else:
        # Use the new OpenAI client initialization style (>= v1.0)
        openai_client = openai.AsyncOpenAI(api_key=api_key)
        logger.info("OpenAI Async Client initialized.")

except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
    openai_client = None # Ensure it's None if init fails

# --- Prompt Design ---
# Keep it short, clear, and focused on a YES/NO answer.
# Using system prompts is generally better for instructions.
SYSTEM_PROMPT = """
You are a game judge. Determine if concept X logically beats concept Y in a creative guessing game like Rock Paper Scissors, but more abstract.
Respond ONLY with the word YES or the word NO. No explanations.
"""
MAX_TOKENS_RESPONSE = 5 # Allow a little buffer for YES/NO

# --- Retry Logic ---
# Exponential backoff with jitter for API calls
@retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(3))
async def generate_ai_verdict(current_word: str, user_guess: str) -> bool:
    """
    Calls the configured AI provider to determine if user_guess beats current_word.

    Returns:
        bool: True if the AI responds with YES, False otherwise (including NO or errors).
    """
    if not openai_client:
         logger.error("AI Client is not initialized. Cannot get verdict.")
         return False # Fail safe

    logger.info(f"Calling AI: Does '{user_guess}' beat '{current_word}'?")

    prompt = f"X = {user_guess}\nY = {current_word}"

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo", # Or choose another suitable model
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=MAX_TOKENS_RESPONSE,
            temperature=0.2, # Low temperature for consistent YES/NO
            n=1, # We only need one answer
            stop=None # Let the model decide when to stop (should be after YES/NO)
        )

        ai_response_text = response.choices[0].message.content.strip().upper()
        logger.info(f"AI raw response: '{ai_response_text}'")

        # --- Parse the Response ---
        if ai_response_text.startswith("YES"):
            logger.info("AI Verdict: YES")
            return True
        elif ai_response_text.startswith("NO"):
            logger.info("AI Verdict: NO")
            return False
        else:
            # Handle unexpected responses
            logger.warning(f"AI gave unexpected response: '{ai_response_text}'. Interpreting as NO.")
            return False

    except openai.APIError as e:
        logger.error(f"OpenAI API error: {e}", exc_info=True)
        return False # Treat API errors as NO
    except Exception as e:
        # Catch other potential errors (network issues, timeouts etc.)
        logger.error(f"Error calling AI: {e}", exc_info=True)
        # The @retry decorator will handle retrying based on exceptions
        raise # Re-raise the exception to trigger tenacity's retry logic

# Example of how to call it (will be used in game_routes.py)
# async def main():
#     result = await generate_ai_verdict("Rock", "Paper")
#     print(f"Result: {result}")
# if __name__ == "__main__":
#     asyncio.run(main())