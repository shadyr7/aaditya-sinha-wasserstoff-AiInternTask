# tests/e2e_duplicate_test.py
import pytest
import httpx # Async HTTP client
import asyncio

# Base URL of the running FastAPI application
# Assumes the app is running locally on port 8000 before the test is run
# Either via 'uvicorn' or 'docker-compose up'
BASE_URL = "http://127.0.0.1:8000"
API_URL = f"{BASE_URL}/game/guess"

# Mark the test function as async using pytest-asyncio
@pytest.mark.asyncio
async def test_duplicate_guess_ends_game():
    """
    E2E Test: Verifies that guessing a word already used in the current
    session results in a 'Game Over' response.
    """
    # Use httpx.AsyncClient for making async requests
    async with httpx.AsyncClient(timeout=10.0) as client: # Added timeout to client
        session_id = None
        current_word = "Rock"
        next_guess = "Paper" # Guess 1

        # --- Guess 1: Start the game (Rock -> Paper) ---
        print(f"\n[Test] Guess 1: {next_guess} vs {current_word}")
        response1 = await client.post(
            API_URL, # Test with default serious persona
            json={
                "current_word": current_word,
                "user_guess": next_guess,
                "session_id": session_id
            }
        )
        print(f"[Test] Response 1 Status: {response1.status_code}")
        print(f"[Test] Response 1 Body: {response1.text}")
        assert response1.status_code == 200, f"Expected 200 OK, got {response1.status_code}"
        data1 = response1.json()
        assert data1["game_over"] is False, "Game should not be over after first guess"
        assert data1["next_word"] is not None, "Next word should be set"
        assert data1["next_word"].lower() == next_guess.lower(), f"Expected next word '{next_guess}', got '{data1['next_word']}'"
        assert data1["score"] == 1, f"Expected score 1, got {data1['score']}"
        assert data1["session_id"] is not None, "Session ID should be returned"
        session_id = data1["session_id"]
        current_word = data1["next_word"]
        print(f"[Test] Session ID: {session_id}, Next Word: {current_word}, Score: {data1['score']}")

        await asyncio.sleep(0.1) # Small delay

        # --- Guess 2: Continue the game (Paper -> Scissors) ---
        next_guess = "Scissors"
        print(f"\n[Test] Guess 2: {next_guess} vs {current_word}")
        response2 = await client.post(
            API_URL,
            json={
                "current_word": current_word,
                "user_guess": next_guess,
                "session_id": session_id
            }
        )
        print(f"[Test] Response 2 Status: {response2.status_code}")
        print(f"[Test] Response 2 Body: {response2.text}")
        assert response2.status_code == 200, f"Expected 200 OK, got {response2.status_code}"
        data2 = response2.json()
        assert data2["game_over"] is False, "Game should not be over after second guess"
        assert data2["next_word"] is not None, "Next word should be set"
        assert data2["next_word"].lower() == next_guess.lower(), f"Expected next word '{next_guess}', got '{data2['next_word']}'"
        assert data2["score"] == 2, f"Expected score 2, got {data2['score']}"
        current_word = data2["next_word"]
        print(f"[Test] Next Word: {current_word}, Score: {data2['score']}")

        await asyncio.sleep(0.1) # Small delay

        # --- Guess 3: DUPLICATE GUESS (Scissors -> Paper) ---
        duplicate_guess = "Paper" # This was used in Guess 1
        print(f"\n[Test] Guess 3 (Duplicate): {duplicate_guess} vs {current_word}")
        response3 = await client.post(
            API_URL,
            json={
                "current_word": current_word, # Should be Scissors
                "user_guess": duplicate_guess, # Trying Paper again
                "session_id": session_id
            }
        )
        print(f"[Test] Response 3 Status: {response3.status_code}")
        print(f"[Test] Response 3 Body: {response3.text}")
        assert response3.status_code == 200, f"Expected 200 OK for Game Over, got {response3.status_code}"
        data3 = response3.json()
        assert data3["game_over"] is True, "Game should be marked as over"
        assert data3["score"] == 2, f"Score should remain 2 after duplicate, got {data3['score']}"

        # --- *** CORRECTED ASSERTION for message content *** ---
        # Check if message indicates game over/terminated due to duplicate
        message_lower = data3["message"].lower()
        assert "game over" in message_lower or "game terminated" in message_lower or "duplicate entry" in message_lower, \
            f"Expected 'Game Over' or similar indication in message, got: {data3['message']}"
        assert f"'{duplicate_guess.lower()}'" in message_lower, \
            f"Expected duplicate word '{duplicate_guess.lower()}' mentioned in message, got: {data3['message']}"
        # --- *** END CORRECTION *** ---

        print(f"[Test] Game Over correctly triggered by duplicate guess '{duplicate_guess}'. Test Passed!")