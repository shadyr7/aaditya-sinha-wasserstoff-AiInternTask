# backend/core/limiter.py
import os
from slowapi import Limiter
from slowapi.util import get_remote_address

# Define the key function once
key_func = get_remote_address

# Initialize with a default (memory) that gets replaced in main.py lifespan
# This INSTANCE will be imported by main.py and game_routes.py
limiter = Limiter(key_func=key_func, storage_uri="memory://")

# Function to update the global limiter instance AFTER redis connects
# Called from main.py's lifespan
def update_limiter_storage(redis_url: str):
    global limiter
    # Re-bind the global 'limiter' variable to a new instance with Redis storage
    limiter = Limiter(key_func=key_func, storage_uri=redis_url)
    # No logging here, main.py will log