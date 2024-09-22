import requests
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import backoff

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# EFP API base URL
EFP_API_BASE = "https://api.ethfollow.xyz/api/v1"

# Constants
MAX_WORKERS = 10
RATE_LIMIT_DELAY = 0.1
MAX_RETRIES = 3

def load_config():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return config['watchlist']

@backoff.on_exception(backoff.expo, requests.RequestException, max_tries=MAX_RETRIES)
def get_endpoint_data(user, endpoint):
    url = f"{EFP_API_BASE}/users/{user}/{endpoint}"
    response = requests.get(url)
    if response.status_code == 404:
        logging.warning(f"404 Not Found for user {user} at endpoint {endpoint}")
        return endpoint, None
    response.raise_for_status()
    return endpoint, response.json()

def get_paginated_data(user, endpoint):
    all_data = []
    offset = 0
    limit = 100  # Adjust based on API limits
    while True:
        url = f"{EFP_API_BASE}/users/{user}/{endpoint}?offset={offset}&limit={limit}"
        response = requests.get(url)
        if response.status_code == 404:
            logging.warning(f"404 Not Found for user {user} at paginated endpoint {endpoint}")
            return endpoint, None
        data = response.json()
        all_data.extend(data.get(endpoint, []))
        if len(data.get(endpoint, [])) < limit:
            break
        offset += limit
    return endpoint, all_data

def get_user_data(user):
    user_data = {}
    endpoints = ['details', 'stats', 'lists', 'following', 'ens', 'account']

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_endpoint = {
            executor.submit(get_endpoint_data, user, endpoint): endpoint 
            for endpoint in endpoints if endpoint != 'following'
        }
        future_to_endpoint[executor.submit(get_paginated_data, user, 'following')] = 'following'

        for future in as_completed(future_to_endpoint):
            endpoint, data = future.result()
            if data is not None:
                user_data[endpoint] = data
                logging.info(f"Successfully fetched {endpoint} data for {user}")
            else:
                logging.warning(f"Failed to fetch {endpoint} data for {user}")

    return user, user_data

def validate_user_data(user_data):
    required_keys = ['details', 'stats', 'lists', 'following']
    return all(key in user_data for key in required_keys)

def save_state(state, filename='initial_state.json'):
    with open(filename, 'w') as f:
        json.dump(state, f, indent=2)
    logging.info(f"State saved to {filename}")

def main():
    watchlist = load_config()
    initial_state = {}
    failing_users = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_user = {executor.submit(get_user_data, user): user for user in watchlist}
        for future in tqdm(as_completed(future_to_user), total=len(watchlist), desc="Fetching user data"):
            user, data = future.result()
            if data and validate_user_data(data):
                initial_state[user] = data
                logging.info(f"Successfully processed data for {user}")
            else:
                failing_users.add(user)
                logging.warning(f"Failed to fetch complete data for user {user}")

    if initial_state:
        save_state(initial_state)
    else:
        logging.error("No data was successfully fetched. initial_state.json was not created.")
    
    if failing_users:
        logging.warning(f"Users with incomplete data: {', '.join(failing_users)}")
    
    logging.info("Initial state download completed.")

if __name__ == "__main__":
    main()