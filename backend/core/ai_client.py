# backend/core/ai_client.py
import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai
# Import types for configuration if needed, or use dictionaries
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import asyncio
from tenacity import retry, stop_after_attempt, wait_random_exponential
import google.api_core.exceptions # For specific error handling

logger = logging.getLogger(__name__)
load_dotenv()

# --- Configure Gemini Client ---
gemini_model = None
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not found in environment variables.")
        # raise ValueError("GEMINI_API_KEY environment variable not set.")
    else:
        genai.configure(api_key=api_key)
        # Choose a suitable model - gemini-1.5-flash is often fast and capable enough
        gemini_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            # System instructions can guide the model's behavior
            system_instruction="You are a game judge. Determine if concept X logically beats concept Y in a creative guessing game like Rock Paper Scissors, but more abstract. Respond ONLY with the word YES or the word NO. No explanations."
            )
        logger.info("Google Generative AI Client configured with model gemini-1.5-flash.")

except Exception as e:
    logger.error(f"Failed to configure Google Generative AI client: {e}", exc_info=True)
    gemini_model = None # Ensure it's None if init fails

# --- Generation Configuration ---
# Keep it focused on YES/NO
generation_config = genai.types.GenerationConfig(
    # candidate_count=1, # Default is 1
    max_output_tokens=10, # Small buffer for YES/NO
    temperature=0.1 # Low temperature for deterministic YES/NO
)

# --- Safety Settings ---
# Relax safety settings slightly if needed for game terms, but be careful.
# BLOCK_NONE might be too permissive for disallowed content filtering later.
# Adjust based on testing. Start with less blocking for game logic.
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

# --- Retry Logic ---
# Exponential backoff with jitter for API calls
# Catching Google API specific exceptions might be useful for retry logic
RETRYABLE_ERRORS = (
    google.api_core.exceptions.ResourceExhausted, # Rate limits
    google.api_core.exceptions.ServiceUnavailable, # Temporary server issues
    google.api_core.exceptions.DeadlineExceeded, # Timeout within Google lib
    # asyncio.TimeoutError # Handled by wait_for in game_routes
)

@retry(
    wait=wait_random_exponential(min=1, max=10),
    stop=stop_after_attempt(3),
    retry_error_callback=lambda retry_state: logger.warning(f"Retrying AI call due to {retry_state.outcome.exception()}...")
    # You could potentially add retry based on specific exceptions: retry=retry_if_exception_type(RETRYABLE_ERRORS)
)
async def generate_ai_verdict(current_word: str, user_guess: str) -> bool:
    """
    Calls the configured Google Gemini model to determine if user_guess beats current_word.

    Returns:
        bool: True if the AI responds with YES, False otherwise (including NO or errors).
    """
    if not gemini_model:
         logger.error("Gemini Client (Model) is not initialized. Cannot get verdict.")
         return False # Fail safe

    logger.info(f"Calling Gemini AI: Does '{user_guess}' beat '{current_word}'?")

    # Gemini prefers direct prompting in the content
    prompt = f"X = {user_guess}\nY = {current_word}\nDoes X beat Y? Answer YES or NO."

    try:
        # Use the async version of generate_content
        response = await gemini_model.generate_content_async(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings,
            # request_options={"timeout": 15} # Timeout can be set here too
        )

        # Debug: Log the full response structure if needed
        # logger.debug(f"Gemini full response object: {response}")

        # --- Parse the Response ---
        # Check if the response was blocked or has no text
        if not response.parts:
             if response.prompt_feedback.block_reason:
                  logger.warning(f"Gemini response blocked. Reason: {response.prompt_feedback.block_reason}. Prompt: '{prompt}'")
             else:
                  logger.warning(f"Gemini response has no parts (potentially empty). Prompt: '{prompt}'")
             return False # Treat blocked/empty responses as NO

        ai_response_text = response.text.strip().upper()
        logger.info(f"Gemini AI raw response text: '{ai_response_text}'")

        if ai_response_text.startswith("YES"):
            logger.info("Gemini AI Verdict: YES")
            return True
        elif ai_response_text.startswith("NO"):
            logger.info("Gemini AI Verdict: NO")
            return False
        else:
            # Handle unexpected responses
            logger.warning(f"Gemini AI gave unexpected response: '{ai_response_text}'. Interpreting as NO.")
            return False

    except google.api_core.exceptions.InvalidArgument as e:
        # Often due to bad safety settings or prompt issues not caught by block_reason
        logger.error(f"Gemini Invalid Argument error: {e}", exc_info=True)
        return False
    except google.api_core.exceptions.ResourceExhausted as e:
        # Rate limiting
        logger.error(f"Gemini API rate limit hit (Resource Exhausted): {e}", exc_info=True)
        raise # Re-raise to trigger tenacity retry
    except google.api_core.exceptions.GoogleAPIError as e:
        # Catch other specific Google API errors
        logger.error(f"Google API error: {e}", exc_info=True)
        raise # Re-raise to trigger tenacity retry
    except Exception as e:
        # Catch other potential errors (network issues, timeouts handled by wait_for, etc.)
        logger.error(f"Error calling Gemini AI: {e}", exc_info=True)
        # Re-raise the exception to potentially trigger tenacity's retry logic
        # or be caught by the asyncio.TimeoutError in game_routes
        raise

# Example of how to call it (for standalone testing if needed)
# async def main():
#     # Make sure GEMINI_API_KEY is in .env
#     result = await generate_ai_verdict("Rock", "Paper")
#     print(f"Result for Paper vs Rock: {result}")
#     result = await generate_ai_verdict("Fire", "Water")
#     print(f"Result for Water vs Fire: {result}")
#
# if __name__ == "__main__":
#     asyncio.run(main())