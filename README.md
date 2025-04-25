# GenAI "What Beats Rock?" Game

A containerized, interactive web game where users chain concepts based on AI validation. Built as an internship assessment task for Wasserstoff, focusing on backend development, AI integration, and deployment practices.

## Features

*   **Core Game Logic:** Guess words that conceptually "beat" the current word in a chain reaction starting from "Rock".
*   **AI Validation:** Uses the Google Gemini API to determine if a guess logically beats the current word.
*   **Session Management:** Tracks individual game progress (word chain, score) using Redis Lists and Hashes.
*   **Duplicate Prevention:** Ends the game if a user repeats a word already used *in the current session's chain*.
*   **AI Verdict Caching:** Caches responses from the Gemini API in Redis to improve performance and reduce API calls.
*   **Global Counters:** Persists the total count for each successfully guessed word across all games in a PostgreSQL database.
*   **Selectable Personas:** Allows users to choose between different host response styles (e.g., Serious, Cheery) via a query parameter.
*   **Moderation:** Filters user guesses for profanity before processing.
*   **Rate Limiting:** Implemented sensible per-IP rate limits using SlowAPI and Redis. *(Adjust wording if implementation was removed)*
*   **Frontend:** Simple, functional web interface built with HTML, CSS (Bootstrap), and vanilla JavaScript.
*   **Containerized:** Runs as a multi-container application (Backend, DB, Cache) using Docker and Docker Compose.
*   **(Optional) Live Demo:** [Link to your Render deployment URL here]

## Technology Stack

*   **Backend:** Python, FastAPI (Async)
*   **AI:** Google Gemini API (`google-generativeai` library)
*   **Database:** PostgreSQL (`asyncpg` driver)
*   **Cache / Session Store:** Redis (`redis-py` async)
*   **Rate Limiting:** SlowAPI
*   **Moderation:** better-profanity
*   **Containerization:** Docker, Docker Compose
*   **Frontend:** HTML, CSS, JavaScript, Bootstrap 5
*   **Testing:** Pytest, HTTPX

## Setup & Running Locally (Docker Compose)

1.  **Prerequisites:**
    *   Git
    *   Docker Desktop (or Docker Engine + Docker Compose) installed and running.

2.  **Clone Repository:**
    ```bash
    git clone https://github.com/shadyr7/aaditya-sinha/wasserstoff/AiInternTask
    ```

3.  **Create `.env` File:**
    *   Copy the example environment file: `cp .env.sample .env` (on Linux/macOS/Git Bash) or `copy .env.sample .env` (on Windows CMD).
    *   **Edit the `.env` file:**
        *   You **MUST** add your Google Gemini API key: `GEMINI_API_KEY=YOUR_API_KEY_HERE`
        *   You can change the `POSTGRES_PASSWORD` if desired (but ensure it matches any existing `local-postgres` volume if you ran manually before).
    *   *Note: The `.env` file is listed in `.gitignore` and should not be committed.*

4.  **Build and Run Containers:**
    ```bash
    docker-compose up --build -d
    ```
    *   `--build`: Builds the backend image if it doesn't exist or if the Dockerfile/code changed.
    *   `-d`: Runs the containers in detached (background) mode.
    *   Wait a minute for the database to initialize on the first run.

5.  **Access Application:**
    *   Open your web browser and navigate to `http://localhost:8000`.

6.  **Stopping Application:**
    ```bash
    docker-compose down
    ```
    *   To also remove the persistent data volumes (Redis cache, DB data): `docker-compose down -v`

## How to Play

1.  The game starts with the word "Rock".
2.  In the input box, type a word or concept that you think "beats" the current word (e.g., "Paper").
3.  Click "Submit Guess".
4.  The AI will judge if your guess logically beats the current word.
5.  If successful, your guess becomes the new current word, your score increases, and the global count for that word is shown.
6.  If the AI disagrees, you need to try guessing something else against the *same* current word.
7.  If you guess a word that you have *already successfully used* in your current game session chain, the game is **Over**.
8.  You can optionally select a "Host Persona" (Serious/Cheery) to change the tone of the feedback messages.

## Architectural Choices

*   **FastAPI:** Chosen for its high performance, asynchronous capabilities (suitable for I/O-bound tasks like API calls and DB access), and automatic OpenAPI documentation.
*   **Redis:** Used for its speed as an in-memory store, ideal for session state (lists/scores) and caching frequently accessed AI verdicts.
*   **PostgreSQL:** A robust relational database suitable for reliable, atomic persistence of global counters.
*   **Docker Compose:** Simplifies local development and deployment setup by defining and managing the multi-container application stack (backend, DB, cache).

## Prompt Design

The core prompt sent to the Gemini API focuses on getting a simple binary decision: