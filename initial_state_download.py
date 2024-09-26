import asyncio
import aiohttp
import json
import logging
import time
import os
from tqdm import tqdm
from datetime import datetime
from cachetools import TTLCache

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
EFP_API_BASE = "https://api.ethfollow.xyz/api/v1"
CONFIG_FILE = 'config.json'
STATE_FILE = 'initial_state.json'
RATE_LIMIT_DELAY = 0.1
MAX_CONCURRENT_REQUESTS = 20
CACHE_TTL = 3600  # 1 hour cache TTL

# Initialize cache
cache = TTLCache(maxsize=1000, ttl=CACHE_TTL)

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            return config['watchlist']
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON in {CONFIG_FILE}")
        return []
    except FileNotFoundError:
        logging.error(f"{CONFIG_FILE} not found")
        return []

async def fetch_endpoint_data(session, endpoint, params=None):
    url = f"{EFP_API_BASE}/{endpoint}"
    try:
        async with session.get(url, params=params, timeout=30) as response:
            response.raise_for_status()
            await asyncio.sleep(RATE_LIMIT_DELAY)
            return await response.json()
    except aiohttp.ClientResponseError as e:
        if e.status == 404:
            logging.warning(f"Resource not found for endpoint {endpoint}")
        else:
            logging.error(f"HTTP error for endpoint {endpoint}: {str(e)}")
    except aiohttp.ClientError as e:
        logging.error(f"Request failed for endpoint {endpoint}: {str(e)}")
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for endpoint {endpoint}: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error for endpoint {endpoint}: {str(e)}")
    return None

async def get_paginated_data(session, endpoint, key):
    all_data = []
    offset = 0
    limit = 100
    while True:
        data = await fetch_endpoint_data(session, endpoint, params={'offset': offset, 'limit': limit})
        if data is None or key not in data:
            break
        new_data = data[key]
        all_data.extend(new_data)
        if len(new_data) < limit:
            break
        offset += limit
    return all_data

async def get_user_data(session, user, fetch_detailed=True):
    start_time = time.time()
    logging.info(f"Starting to fetch data for {user}")
    user_data = {}

    details = await fetch_endpoint_data(session, f"users/{user}/details")
    user_data['has_profile'] = bool(details)
    user_data['primary_list'] = details.get('primary_list') if details else None
    user_data['has_active_account'] = user_data['primary_list'] is not None

    if not fetch_detailed:
        return user, user_data

    endpoints = [
        (f"users/{user}/details", 'details', False),
        (f"users/{user}/stats", 'stats', False),
        (f"users/{user}/followers", 'followers', True),
        (f"users/{user}/following", 'following', True),
        (f"users/{user}/tags", 'tags', False),
        (f"users/{user}/ens", 'ens', False)
    ]

    if user_data['primary_list']:
        endpoints.extend([
            (f"lists/{user_data['primary_list']}/stats", 'list_stats', False),
            (f"lists/{user_data['primary_list']}/allFollowingAddresses", 'allFollowingAddresses', False)
        ])

    tasks = [
        get_paginated_data(session, endpoint, key) if is_paginated else fetch_endpoint_data(session, endpoint)
        for endpoint, key, is_paginated in endpoints
    ]
    results = await asyncio.gather(*tasks)

    for (_, key, _), data in zip(endpoints, results):
        if data is not None:
            user_data[key] = data
            logging.info(f"Successfully fetched {key} data for {user}. Data size: {len(str(data))} characters")
        else:
            logging.warning(f"Failed to fetch data for {key}")

    end_time = time.time()
    logging.info(f"Finished fetching data for {user}. Time taken: {end_time - start_time:.2f} seconds")
    return user, user_data

def validate_user_data(user_data):
    if not user_data.get('has_profile', False):
        return True  # Consider users without a profile as valid
    required_keys = ['details', 'stats', 'followers', 'following', 'tags', 'ens']
    if user_data.get('has_active_account', False):
        required_keys.extend(['list_stats', 'allFollowingAddresses'])
    return all(key in user_data and user_data[key] is not None for key in required_keys)

def save_state(state):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_filename = f'initial_state_{timestamp}.json'
    try:
        with open(timestamped_filename, 'w') as f:
            json.dump(state, f, indent=2)
        logging.info(f"State saved to {timestamped_filename}")

        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        logging.info(f"State also saved to {STATE_FILE}")

        if os.path.getsize(STATE_FILE) == 0:
            logging.error(f"Error: {STATE_FILE} is empty after writing")
        if os.path.getsize(timestamped_filename) == 0:
            logging.error(f"Error: {timestamped_filename} is empty after writing")
    except IOError as e:
        logging.error(f"Error saving state: {str(e)}")

async def process_user(session, user):
    try:
        _, user_data = await get_user_data(session, user, fetch_detailed=True)
        if validate_user_data(user_data):
            return user, user_data, 'success'
        else:
            return user, user_data, 'incomplete'
    except Exception as e:
        logging.error(f"Error while fetching data for user {user}: {str(e)}")
        return user, None, 'error'

async def initial_state_download():
    watchlist = load_config()
    if not watchlist:
        logging.error("No users in watchlist. Exiting.")
        return

    initial_state = {}
    failing_users = set()
    users_without_profile = set()
    users_without_active_account = set()
    active_users = set()

    async with aiohttp.ClientSession() as session:
        tasks = [process_user(session, user) for user in watchlist]
        results = await asyncio.gather(*tasks)

    for user, user_data, status in results:
        if status == 'success':
            initial_state[user] = user_data
            if user_data.get('has_active_account', False):
                active_users.add(user)
            elif not user_data.get('has_profile', False):
                users_without_profile.add(user)
            else:
                users_without_active_account.add(user)
        else:
            failing_users.add(user)

    if initial_state:
        save_state(initial_state)
    else:
        logging.error("No data was successfully fetched. initial_state.json was not created.")
    
    if failing_users:
        logging.warning(f"Users with incomplete data: {', '.join(failing_users)}")
    
    logging.info(f"Total users processed: {len(watchlist)}")
    logging.info(f"Active users: {len(active_users)}")
    logging.info(f"Users without profile: {len(users_without_profile)}")
    logging.info(f"Users without active account: {len(users_without_active_account)}")
    logging.info(f"Failed users: {len(failing_users)}")
    logging.info("Initial state download completed.")

if __name__ == "__main__":
    asyncio.run(initial_state_download())