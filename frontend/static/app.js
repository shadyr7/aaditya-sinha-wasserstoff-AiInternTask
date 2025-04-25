// frontend/app.js
document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const currentWordEl = document.getElementById('current-word');
    const userGuessInput = document.getElementById('user-guess');
    const guessForm = document.getElementById('guess-form');
    const currentScoreEl = document.getElementById('current-score');
    const globalCountEl = document.getElementById('global-count');
    const gameStatusEl = document.getElementById('game-status');
    const statusIconArea = document.getElementById('status-icon-area'); // Get new element
    const statusMessageEl = document.getElementById('status-message');
    // const feedbackEmojiEl = document.getElementById('feedback-emoji'); // No longer needed directly
    const guessHistoryEl = document.getElementById('guess-history');
    const personaSelect = document.getElementById('persona-select');

    // --- Game State ---
    let currentWord = 'Rock'; // Initial word
    let sessionId = null;
    let score = 0;
    let history = ['Game Started']; // Local history for display
    const MAX_HISTORY_ITEMS = 6; // Display last few items

    // --- API Configuration ---
    const API_BASE_URL = '/'; // Use relative path assuming frontend served from backend root

    // --- Functions ---
    function updateUI() {
        currentWordEl.textContent = currentWord;
        currentScoreEl.textContent = score;

        // Update History List (show last MAX_HISTORY_ITEMS)
        guessHistoryEl.innerHTML = ''; // Clear previous history
        const recentHistory = history.slice(-MAX_HISTORY_ITEMS);
        recentHistory.reverse().forEach(item => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.style.backgroundColor = 'inherit';
            li.style.color = 'inherit';
            li.style.borderColor = '#444';
            li.textContent = item;
            guessHistoryEl.appendChild(li);
        });
    }

    // *** UPDATED setStatus Function ***
    function setStatus(message, statusType = 'info') {
        // statusType can be 'info', 'success', 'ai-fail', 'game-over'
        statusMessageEl.textContent = message;

        // Clear old icon/emoji content if using ::before pseudo-elements
        // If you were directly manipulating an emoji span, clear it here:
        // feedbackEmojiEl.textContent = ''; // Clear old emoji if needed
        statusIconArea.innerHTML = ''; // Clear if using ::before for icons

        // Remove previous status classes
        gameStatusEl.classList.remove('status-info', 'status-success', 'status-ai-fail', 'status-game-over', 'loading');

        // Add the new status class based on type
        switch (statusType) {
            case 'success':
                gameStatusEl.classList.add('status-success');
                break;
            case 'ai-fail':
                gameStatusEl.classList.add('status-ai-fail');
                break;
            case 'game-over':
                gameStatusEl.classList.add('status-game-over');
                break;
            case 'info':
            default:
                gameStatusEl.classList.add('status-info');
                break;
        }
    }


    async function handleGuessSubmit(event) {
        event.preventDefault();
        const userGuess = userGuessInput.value.trim();
        if (!userGuess) return;

        // Add loading state class (optional, ensure defined in CSS)
        // gameStatusEl.classList.add('loading');
        setStatus('Thinking...', 'info'); // Use 'info' status type
        userGuessInput.disabled = true;
        guessForm.querySelector('button').disabled = true;

        const selectedPersona = personaSelect.value;
        const url = `${API_BASE_URL}game/guess?persona=${selectedPersona}`;

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                body: JSON.stringify({
                    current_word: currentWord,
                    user_guess: userGuess,
                    session_id: sessionId,
                }),
            });

            const data = await response.json();
            let statusType = 'info'; // Default status

            if (!response.ok) {
                statusType = 'game-over'; // Treat API errors as game-ending state
                setStatus(data.detail || `Error: ${response.statusText}`, statusType);
                // Potentially reset local state or UI further based on specific errors
            } else {
                // Determine status type based on successful response
                if (data.game_over) {
                    statusType = 'game-over';
                } else if (data.next_word === userGuess) { // Correct guess, game continues
                    statusType = 'success';
                } else { // Incorrect guess (AI said NO), game continues
                    statusType = 'ai-fail';
                }

                setStatus(data.message, statusType); // Set status class and message

                // Update game state variables
                currentWord = data.next_word || currentWord; // Update current word on success
                score = data.score;
                sessionId = data.session_id; // Always update session ID
                globalCountEl.textContent = data.global_count !== null ? data.global_count : '-';

                // Update local history display
                if (statusType === 'success') {
                    history.push(userGuess);
                } else if (statusType === 'game-over') {
                     // Add the guess that caused game over, if available in message
                    const triggeringGuess = data.message.includes(userGuess) ? userGuess : "(duplicate)";
                    history.push(`❌ Game Over (${triggeringGuess})`);
                } // No history update for AI fail needed unless desired

                updateUI(); // Refresh displayed word, score, history

                // Handle UI state after response
                if (data.game_over) {
                    userGuessInput.disabled = true;
                    guessForm.querySelector('button').disabled = true;
                    currentWordEl.textContent = "- GAME OVER -";
                    currentWordEl.classList.add("text-danger"); // Make "Game Over" red
                } else {
                     userGuessInput.value = ''; // Clear input for next guess
                }
            }
        } catch (error) {
            console.error('Fetch error:', error);
            setStatus(`Network or server error: ${error.message}`, 'game-over'); // Use 'game-over' style for network errors
        } finally {
            // Re-enable form IF the game isn't over
            // Check class directly for robustness
             if (!gameStatusEl.classList.contains('status-game-over')) {
                userGuessInput.disabled = false;
                guessForm.querySelector('button').disabled = false;
                userGuessInput.focus();
            }
        }
    }

    // --- Initial Setup ---
    guessForm.addEventListener('submit', handleGuessSubmit);
    updateUI(); // Set initial word/score display
    setStatus("Enter a word that conceptually 'beats' Rock!", 'info'); // Initial info message
    userGuessInput.focus();
});