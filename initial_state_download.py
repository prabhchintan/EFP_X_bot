import requests
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# EFP API base URL
EFP_API_BASE = "https://api.ethfollow.xyz/api/v1"

# Constants
MAX_WORKERS = 10
RATE_LIMIT_DELAY = 0.1  # Reduced from 0.2 to 0.1
MAX_RETRIES = 3

def load_config():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return config['watchlist']

def get_endpoint_data(user, endpoint):
    url = f"{EFP_API_BASE}/users/{user}/{endpoint}"
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url)
            response.raise_for_status()
            return endpoint, response.json()
        except requests.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                logging.warning(f"Error fetching {endpoint} for {user} after {MAX_RETRIES} attempts: {e}")
                return endpoint, None
        time.sleep(RATE_LIMIT_DELAY)

def get_user_data(user):
    user_data = {}
    endpoints = ['details', 'stats', 'lists', 'following']

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_endpoint = {executor.submit(get_endpoint_data, user, endpoint): endpoint for endpoint in endpoints}
        for future in as_completed(future_to_endpoint):
            endpoint, data = future.result()
            if data is not None:
                user_data[endpoint] = data

    return user, user_data

def save_state(state, filename='initial_state.json'):
    with open(filename, 'w') as f:
        json.dump(state, f, indent=2)
    logging.info(f"State saved to {filename}")

def main():
    watchlist = load_config()
    initial_state = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_user = {executor.submit(get_user_data, user): user for user in watchlist}
        for future in tqdm(as_completed(future_to_user), total=len(watchlist), desc="Fetching user data"):
            user, data = future.result()
            if data:  # Only add users with data
                initial_state[user] = data

    save_state(initial_state)
    logging.info("Initial state download completed.")

if __name__ == "__main__":
    main()