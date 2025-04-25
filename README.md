# GenAI "What Beats Rock?" Game

A containerized, interactive web game where users chain concepts based on AI validation. Built as an internship assessment task for Wasserstoff, focusing on backend development, AI integration, and deployment practices.

## Live Demo

The application is deployed on Render (using Upstash for Redis) and can be accessed here:

**https://genai-whobeatsrock-aadityasinha.onrender.com** 
*(Replace with your actual Render URL)*

*(Note: The free tier service may spin down after inactivity, so the first load might take up to a minute.)*

## Features

*   **Core Game Logic:** Guess words that conceptually "beat" the current word in a chain reaction starting from "Rock".
*   **AI Validation:** Uses the Google Gemini API to determine if a guess logically beats the current word.
*   **Session Management:** Tracks individual game progress (word chain, score) using Redis Lists and key expiration (TTL).
*   **Duplicate Prevention:** Ends the game if a user repeats a word already used *in the current session's chain*.
*   **AI Verdict Caching:** Caches responses from the Gemini API in Redis (with TTL) to improve performance and reduce API calls.
*   **Global Counters:** Persists the total count for each successfully guessed word across all games in a PostgreSQL database (using atomic increments).
*   **Selectable Personas:** Allows users to choose between different host response styles (Serious, Cheery) via a query parameter, affecting feedback messages.
*   **Moderation:** Filters user guesses for profanity (`better-profanity`) before processing.
*   **Rate Limiting:** Implemented sensible per-IP rate limits (e.g., 15 guesses/minute) using SlowAPI and Redis, applied via FastAPI middleware and decorators.
*   **Frontend:** Simple, functional web interface built with HTML, CSS (Bootstrap), and vanilla JavaScript, interacting asynchronously with the backend.
*   **Containerized:** Runs as a multi-container application (Backend, DB, Cache) defined and managed using Docker and Docker Compose.
*   **Cloud Deployed:** Successfully deployed to a Platform-as-a-Service provider (Render + Upstash).

## Technology Stack

*   **Backend:** Python 3.11, FastAPI (Async)
*   **AI:** Google Gemini API (`google-generativeai` library)
*   **Database:** PostgreSQL (`asyncpg` driver)
*   **Cache / Session Store:** Redis (`redis-py` async)
*   **Rate Limiting:** SlowAPI
*   **Moderation:** better-profanity
*   **Containerization:** Docker, Docker Compose
*   **Frontend:** HTML, CSS, JavaScript, Bootstrap 5
*   **Testing:** Pytest, HTTPX, pytest-asyncio
*   **Deployment:** Render (Web Service + PostgreSQL), Upstash (Redis)

## Setup & Running Locally (Docker Compose)

1.  **Prerequisites:**
    *   Git
    *   Docker Desktop (or Docker Engine + Docker Compose) installed and running.

2.  **Clone Repository:**
    ```bash
    # Replace with your actual repository URL if different
    git clone https://github.com/shadyr7/aaditya-sinha-wasserstoff-AiInternTask.git
    cd genai-intern-game
    ```

3.  **Create `.env` File:**
    *   Copy the example environment file: `cp .env.sample .env` (Linux/macOS/Git Bash) or `copy .env.sample .env` (Windows CMD).
    *   **Edit the `.env` file:**
        *   You **MUST** add your Google Gemini API key: `GEMINI_API_KEY=YOUR_API_KEY_HERE`
        *   Set database credentials (the defaults `user`, `password`, `whatbeatsrock_db` will be used by Compose to initialize the DB):
            ```dotenv
            POSTGRES_USER=user
            POSTGRES_PASSWORD=password
            POSTGRES_DB=whatbeatsrock_db
            ```
        *   For local Docker Compose, ensure hosts point to service names:
            ```dotenv
            POSTGRES_HOST=db
            REDIS_HOST=cache
            ```
    *   *Note: The `.env` file is listed in `.gitignore` and should not be committed.*

4.  **Build and Run Containers:**
    ```bash
    docker-compose up --build -d
    ```
    *   `--build`: Builds the backend image if needed.
    *   `-d`: Runs in detached mode.
    *   Wait ~30-60 seconds for the database to initialize on the first run. Check logs with `docker-compose logs -f`.

5.  **Access Application:**
    *   Open your web browser and navigate to `http://localhost:8000`.

6.  **Stopping Application:**
    ```bash
    docker-compose down
    ```
    *   To also remove persistent data volumes: `docker-compose down -v`

## How to Play

1.  The game starts with the word "Rock".
2.  In the input box, type a word or concept that you think "beats" the current word (e.g., "Paper").
3.  Click "Submit Guess".
4.  The AI will judge if your guess logically beats the current word.
5.  If successful, your guess becomes the new current word, your score increases, and the global count for that word is shown.
6.  If the AI disagrees, you need to try guessing something else against the *same* current word.
7.  If you guess a word that you have *already successfully used* in your current game session chain, the game is **Over**.
8.  You can optionally select a "Host Persona" (Serious/Cheery) using the dropdown to change the tone of the feedback messages.

## Architectural Choices

*   **FastAPI:** Chosen for high performance, async capabilities, type hints, data validation via Pydantic, and automatic OpenAPI documentation generation.
*   **Redis:** Utilized for low-latency caching of AI API responses (reducing external calls and cost) and managing ephemeral game session state (guess list, score) with built-in TTL features.
*   **PostgreSQL:** Selected for reliable, persistent storage of relational data (global word counts) and atomic counter updates (`INSERT ... ON CONFLICT ... UPDATE`).
*   **Docker Compose:** Enables easy local development and testing by defining and orchestrating the multi-container (backend, DB, cache) application stack with a single command. Facilitates consistent environments.
*   **PaaS Deployment (Render + Upstash):** Demonstrates deployment to cloud platforms using managed database services (Render Postgres) and external managed caches (Upstash Redis) configured via environment variables, showcasing practical deployment patterns.

## Prompt Design

The core prompt sent to the Gemini API is designed for a concise YES/NO judgment, minimizing token usage and focusing the LLM on the specific task:
You are a game judge. Determine if concept X logically beats concept Y in a creative guessing game like Rock Paper Scissors, but more abstract. Respond ONLY with the word YES or the word NO. No explanations.
X = [User Guess]
Y = [Current Word]
Does X beat Y? Answer YES or NO.