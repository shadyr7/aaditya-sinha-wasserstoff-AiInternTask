# backend/core/moderation.py
import logging
from better_profanity import profanity

logger = logging.getLogger(__name__)

# Load the default word list when the module is first imported.
# You can optionally add custom lists: profanity.add_censor_words([...])
# profanity.load_censor_words() is often called implicitly on first use,
# but calling it explicitly ensures it's ready. Let's rely on implicit load.
logger.info("Profanity filter initialized (using default word list).")

def is_guess_clean(text: str) -> bool:
    """
    Checks if the provided text contains profanity.

    Args:
        text: The text string to check.

    Returns:
        True if the text is clean, False otherwise.
    """
    is_profane = profanity.contains_profanity(text)
    if is_profane:
        logger.warning(f"Profanity detected in guess: '{text}'")
    return not is_profane

# Example usage (optional):
# if __name__ == '__main__':
#     print(f"'Hello friend': {is_guess_clean('Hello friend')}")
#     print(f"'Some bad word': {is_guess_clean('example crap shoot')}") # Example bad words