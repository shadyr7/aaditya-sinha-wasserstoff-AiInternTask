# Dockerfile

# 1. Base Image: Use an official Python slim image
FROM python:3.11-slim

# 2. Set Environment Variables
# Prevents Python from writing pyc files to disc (improves performance in Docker)
ENV PYTHONDONTWRITEBYTECODE 1
# Ensures Python output is sent straight to terminal without buffering
ENV PYTHONUNBUFFERED 1

# 3. Set Working Directory
WORKDIR /app

# 4. Install OS Dependencies (if any - unlikely needed for this project)
# Example: RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# 5. Install Python Dependencies
# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .
# Install using pip, --no-cache-dir reduces image size
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy Application Code
# Copy the backend directory into the container's /app/backend directory
COPY ./backend /app/backend
# Copy the frontend directory (needed for static files and index.html serving)
COPY ./frontend /app/frontend

# 7. Expose Port
# Expose the port the app runs on (matching the Uvicorn command)
EXPOSE 8000

# 8. Define Default Command
# Run Uvicorn. Use 0.0.0.0 to listen on all interfaces inside the container.
# Use --host 0.0.0.0 instead of 127.0.0.1
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "${PORT:-8000}"]