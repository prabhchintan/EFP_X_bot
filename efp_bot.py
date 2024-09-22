import requests
import json
import tweepy
import os
import logging
from dotenv import load_dotenv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import backoff

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# EFP API base URL
EFP_API_BASE = "https://api.ethfollow.xyz/api/v1"

# Twitter setup
twitter_client = tweepy.Client(
    consumer_key=os.getenv("TWITTER_CONSUMER_KEY"),
    consumer_secret=os.getenv("TWITTER_CONSUMER_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
)

# Constants
MAX_WORKERS = 10
MAX_RETRIES = 3
FOLLOWER_CHANGE_THRESHOLD = 10
FOLLOWING_CHANGE_THRESHOLD = 5
TOP_RANK_THRESHOLD = 20

def load_state():
    try:
        with open('initial_state.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("initial_state.json not found. Please run initial_state_download.py first.")
        return {}

def save_state(state):
    with open('initial_state.json', 'w') as f:
        json.dump(state, f, indent=2)

@backoff.on_exception(backoff.expo, requests.RequestException, max_tries=MAX_RETRIES)
def get_endpoint_data(user, endpoint, params=None):
    url = f"{EFP_API_BASE}/users/{user}/{endpoint}"
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def get_paginated_data(user, endpoint):
    all_data = []
    offset = 0
    limit = 100  # Adjust based on API limits
    while True:
        try:
            data = get_endpoint_data(user, endpoint, params={'offset': offset, 'limit': limit})
            all_data.extend(data.get(endpoint, []))
            if len(data.get(endpoint, [])) < limit:
                break
            offset += limit
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logging.warning(f"404 Not Found for user {user} at paginated endpoint {endpoint}")
                return None
            raise
    return all_data

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
            endpoint = future_to_endpoint[future]
            try:
                data = future.result()
                user_data[endpoint] = data
                logging.info(f"Successfully fetched {endpoint} data for {user}")
            except Exception as e:
                logging.error(f"Error fetching {endpoint} for {user}: {e}")
                user_data[endpoint] = None

    return user_data if all(user_data.values()) else None

def detect_changes(old_data, new_data):
    changes = []
    
    if old_data is None and new_data is None:
        return changes
    
    if old_data is None:
        changes.append(("new_user", "New user added to EFP"))
        return changes
    
    if new_data is None:
        return changes

    # Check if a list was created for the first time
    old_lists = old_data.get('lists', {}).get('lists', [])
    new_lists = new_data.get('lists', {}).get('lists', [])
    if not old_lists and new_lists:
        changes.append(("created_list", "created an EFP list"))
    
    # Check for significant follower changes
    old_followers = old_data.get('stats', {}).get('followers', 0)
    new_followers = new_data.get('stats', {}).get('followers', 0)
    follower_change = new_followers - old_followers
    if abs(follower_change) >= FOLLOWER_CHANGE_THRESHOLD:
        changes.append(("follower_change", f"{'gained' if follower_change > 0 else 'lost'} {abs(follower_change)} followers"))
    
    # Check for significant following changes
    old_following = old_data.get('stats', {}).get('following', 0)
    new_following = new_data.get('stats', {}).get('following', 0)
    following_change = new_following - old_following
    if abs(following_change) >= FOLLOWING_CHANGE_THRESHOLD:
        changes.append(("following_change", f"started following {abs(following_change)} accounts"))
    
    # Check for rank changes
    old_rank = old_data.get('stats', {}).get('rank', 0)
    new_rank = new_data.get('stats', {}).get('rank', 0)
    if old_rank > TOP_RANK_THRESHOLD and new_rank <= TOP_RANK_THRESHOLD:
        changes.append(("rank_change", f"entered the top {TOP_RANK_THRESHOLD} ranks"))
    
    # Check for ENS changes
    old_ens = old_data.get('ens', {})
    new_ens = new_data.get('ens', {})
    if old_ens != new_ens:
        changes.append(("ens_change", "Updated ENS data"))

    # Check for account changes
    old_account = old_data.get('account', {})
    new_account = new_data.get('account', {})
    if old_account != new_account:
        changes.append(("account_change", "Updated account details"))

    return changes

def generate_summary_tweet(all_changes):
    if not all_changes:
        return None

    # Sort changes by priority (number of changes) and select the top user
    prioritized_changes = sorted(all_changes, key=lambda x: len(x[1]), reverse=True)
    top_user, top_changes = prioritized_changes[0]

    intro = "🚀 EFP Update Alert! 🚀"
    body = f"{top_user} has been busy: {', '.join([c[1] for c in top_changes[:3]])}"
    
    if len(prioritized_changes) > 1:
        other_users = [user for user, _ in prioritized_changes[1:4]]
        outro = f"Also watch: {', '.join(other_users)}"
    else:
        outro = "Stay tuned for more EFP action! 👀"
    
    tweet = f"{intro}\n\n{body}\n\n{outro}\n\nMore at https://testing.ethfollow.xyz/{top_user}"
    
    return tweet[:280]  # Twitter character limit

def post_tweet(message):
    try:
        response = twitter_client.create_tweet(text=message)
        logging.info(f"Tweet posted successfully! Tweet ID: {response.data['id']}")
    except Exception as e:
        logging.error(f"Error posting tweet: {e}")

def main():
    state = load_state()
    if not state:
        return

    updated_state = {}
    all_changes = []
    failing_users = set()
    
    with tqdm(total=len(state), desc="Processing users") as pbar:
        for user, old_data in state.items():
            new_data = get_user_data(user)
            if new_data is None:
                logging.warning(f"Failed to fetch data for {user}")
                failing_users.add(user)
                updated_state[user] = old_data
            else:
                changes = detect_changes(old_data, new_data)
                
                if changes:
                    all_changes.append((user, changes))
                    updated_state[user] = new_data
                    logging.info(f"Changes detected for {user}: {', '.join([c[1] for c in changes])}")
                else:
                    updated_state[user] = new_data
                    logging.info(f"No changes detected for {user}")
            
            pbar.update(1)
    
    save_state(updated_state)
    logging.info("Processing completed. State updated.")

    if failing_users:
        logging.warning(f"Users with consistently failing data: {', '.join(failing_users)}")

    if all_changes:
        summarized_tweet = generate_summary_tweet(all_changes)
        if summarized_tweet:
            post_tweet(summarized_tweet)
    else:
        logging.info("No changes detected across all users. No tweet posted.")

if __name__ == "__main__":
    main()