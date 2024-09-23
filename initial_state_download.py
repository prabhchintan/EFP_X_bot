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
def make_request(url):
    return requests.get(url, timeout=30)  # Increased timeout to 30 seconds

def get_endpoint_data(user, endpoint):
    url = f"{EFP_API_BASE}/users/{user}/{endpoint}"
    response = make_request(url)
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
        response = make_request(url)
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
    logging.info(f"Starting to fetch data for {user}")
    user_data = {}
    endpoints = ['details', 'stats', 'followers', 'following', 'ens']

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_endpoint = {
            executor.submit(get_endpoint_data, user, endpoint): endpoint 
            for endpoint in endpoints if endpoint not in ['followers', 'following']
        }
        future_to_endpoint[executor.submit(get_paginated_data, user, 'followers')] = 'followers'
        future_to_endpoint[executor.submit(get_paginated_data, user, 'following')] = 'following'

        for future in as_completed(future_to_endpoint):
            endpoint = future_to_endpoint[future]
            logging.info(f"Fetching {endpoint} data for {user}")
            endpoint, data = future.result()
            if data is not None:
                user_data[endpoint] = data
                logging.info(f"Successfully fetched {endpoint} data for {user}")
            else:
                logging.warning(f"Failed to fetch {endpoint} data for {user}")

    logging.info(f"Finished fetching data for {user}")
    return user, user_data

def validate_user_data(user_data):
    required_keys = ['details', 'stats', 'followers', 'following']
    return all(key in user_data for key in required_keys)

def save_state(state, filename='initial_state.json'):
    with open(filename, 'w') as f:
        json.dump(state, f, indent=2)
    logging.info(f"State saved to {filename}")

def save_partial_progress(initial_state, processed_users):
    with open('partial_state.json', 'w') as f:
        json.dump(initial_state, f)
    with open('processed_users.txt', 'w') as f:
        f.write('\n'.join(processed_users))

def load_partial_progress():
    try:
        with open('partial_state.json', 'r') as f:
            initial_state = json.load(f)
        with open('processed_users.txt', 'r') as f:
            processed_users = set(f.read().splitlines())
        return initial_state, processed_users
    except FileNotFoundError:
        return {}, set()

def main():
    initial_state, processed_users = load_partial_progress()
    watchlist = load_config()
    remaining_users = [user for user in watchlist if user not in processed_users]
    failing_users = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_user = {executor.submit(get_user_data, user): user for user in remaining_users}
        for future in tqdm(as_completed(future_to_user), total=len(remaining_users), desc="Fetching user data"):
            user = future_to_user[future]
            try:
                data = future.result(timeout=60)  # Set a 60-second timeout for each user
                if data and validate_user_data(data[1]):
                    initial_state[user] = data[1]
                    logging.info(f"Successfully processed data for {user}")
                else:
                    failing_users.add(user)
                    initial_state[user] = None  # Add failed users to the state with None value
                    logging.warning(f"Failed to fetch complete data for user {user}")
            except Exception as e:
                failing_users.add(user)
                initial_state[user] = None  # Add failed users to the state with None value
                logging.error(f"Error while fetching data for user {user}: {str(e)}")
            
            processed_users.add(user)
            save_partial_progress(initial_state, processed_users)

    if initial_state:
        save_state(initial_state)
    else:
        logging.error("No data was successfully fetched. initial_state.json was not created.")
    
    if failing_users:
        logging.warning(f"Users with incomplete data: {', '.join(failing_users)}")
    
    logging.info(f"Total users processed: {len(initial_state)}")
    logging.info(f"Successful users: {len(initial_state) - len(failing_users)}")
    logging.info(f"Failed users: {len(failing_users)}")
    logging.info("Initial state download completed.")

if __name__ == "__main__":
    main()