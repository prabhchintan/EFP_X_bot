import requests
import json
import tweepy
import os
import time
import logging
from dotenv import load_dotenv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

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
RATE_LIMIT_DELAY = 0.1
MAX_RETRIES = 3
FOLLOWER_CHANGE_THRESHOLD = 10
FOLLOWING_CHANGE_THRESHOLD = 5
TOP_RANK_THRESHOLD = 100

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
    endpoints = ['details', 'stats', 'lists', 'following', 'ens']

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_endpoint = {executor.submit(get_endpoint_data, user, endpoint): endpoint for endpoint in endpoints}
        for future in as_completed(future_to_endpoint):
            endpoint, data = future.result()
            if data is not None:
                user_data[endpoint] = data

    return user_data if user_data else None

def detect_changes(old_data, new_data):
    changes = []
    
    if old_data is None or new_data is None:
        return changes

    # Check if a list was created for the first time
    if not old_data.get('lists', {}).get('lists') and new_data.get('lists', {}).get('lists'):
        changes.append(("created_list", "created an EFP list"))
    
    # Check for follow, unfollow changes
    old_following = set(f['data'] for f in old_data.get('following', {}).get('following', []))
    new_following = set(f['data'] for f in new_data.get('following', {}).get('following', []))
    
    followed = new_following - old_following
    unfollowed = old_following - new_following
    
    for address in followed:
        changes.append(("followed", f"followed {address}"))
    for address in unfollowed:
        changes.append(("unfollowed", f"unfollowed {address}"))
    
    # Check for block and mute changes
    old_button_state = old_data.get('details', {}).get('button_state', {})
    new_button_state = new_data.get('details', {}).get('button_state', {})
    
    if old_button_state.get('is_blocked') != new_button_state.get('is_blocked'):
        changes.append(("block_change", "blocked" if new_button_state.get('is_blocked') else "unblocked"))
    
    if old_button_state.get('is_muted') != new_button_state.get('is_muted'):
        changes.append(("mute_change", "muted" if new_button_state.get('is_muted') else "unmuted"))
    
    # Check for significant follower/following count changes
    old_stats = old_data.get('stats', {})
    new_stats = new_data.get('stats', {})
    
    follower_change = int(new_stats.get('followers_count', 0)) - int(old_stats.get('followers_count', 0))
    following_change = int(new_stats.get('following_count', 0)) - int(old_stats.get('following_count', 0))
    
    if abs(follower_change) >= FOLLOWER_CHANGE_THRESHOLD:
        changes.append(("follower_change", f"{'gained' if follower_change > 0 else 'lost'} {abs(follower_change)} followers"))
    
    if abs(following_change) >= FOLLOWING_CHANGE_THRESHOLD:
        changes.append(("following_change", f"{'started following' if following_change > 0 else 'unfollowed'} {abs(following_change)} accounts"))
    
    # Check for ranking changes
    old_ranks = old_data.get('details', {}).get('ranks', {})
    new_ranks = new_data.get('details', {}).get('ranks', {})
    
    for rank_type in ['mutuals_rank', 'followers_rank', 'following_rank', 'top8_rank']:
        old_rank = int(old_ranks.get(rank_type, 0))
        new_rank = int(new_ranks.get(rank_type, 0))
        if new_rank <= TOP_RANK_THRESHOLD and old_rank > TOP_RANK_THRESHOLD:
            changes.append(("rank_change", f"entered top {TOP_RANK_THRESHOLD} in {rank_type.replace('_rank', '')}"))
    
    # Check for ENS data changes
    old_ens = old_data.get('ens', {})
    new_ens = new_data.get('ens', {})
    
    for field in ['avatar', 'description', 'name']:
        if old_ens.get(field) != new_ens.get(field):
            changes.append(("ens_change", f"updated their ENS {field}"))
    
    return changes

def prioritize_changes(changes):
    priority_order = [
        "created_list",
        "rank_change",
        "follower_change",
        "following_change",
        "followed",
        "unfollowed",
        "block_change",
        "mute_change",
        "ens_change"
    ]
    
    sorted_changes = sorted(changes, key=lambda x: priority_order.index(x[0]) if x[0] in priority_order else len(priority_order))
    return sorted_changes

def generate_tweet(user, changes):
    if not changes:
        return None
    
    prioritized_changes = prioritize_changes(changes)
    main_change = prioritized_changes[0][1]
    
    intro_phrases = [
        f"👀 Looks like {user} has been busy!",
        f"🚀 {user} is making moves!",
        f"💫 Something's stirring in {user}'s EFP world!",
        f"🔥 Hot update from {user}!",
    ]
    
    intro = random.choice(intro_phrases)
    
    body = f"{main_change.capitalize()}"
    
    if len(prioritized_changes) > 1:
        additional_changes = [change[1] for change in prioritized_changes[1:4]]  # Limit to 3 additional changes
        body += f" Also: {', '.join(additional_changes)}"
        if len(prioritized_changes) > 4:
            body += f" and {len(prioritized_changes) - 4} more changes"
    
    outro_phrases = [
        "What's next? 👀",
        "The EFP saga continues! 🍿",
        "Who's watching? 👁️",
        "Feel the pulse of the Ethereum social graph! 💓",
    ]
    
    outro = random.choice(outro_phrases)
    
    tweet = f"{intro}\n\n{body}\n\n{outro}\n\nSee more: https://testing.ethfollow.xyz/{user}"
    
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
    
    with tqdm(total=len(state), desc="Processing users") as pbar:
        for user, old_data in state.items():
            new_data = get_user_data(user)
            if new_data:
                changes = detect_changes(old_data, new_data)
                
                if changes:
                    tweet = generate_tweet(user, changes)
                    if tweet:
                        post_tweet(tweet)
                    
                    updated_state[user] = new_data
                    logging.info(f"Changes detected for {user}: {', '.join([c[1] for c in changes])}")
                else:
                    updated_state[user] = old_data
                    logging.info(f"No changes detected for {user}")
            else:
                updated_state[user] = old_data
                logging.warning(f"Failed to fetch data for {user}")
            
            pbar.update(1)
    
    save_state(updated_state)
    logging.info("Processing completed. State updated.")

if __name__ == "__main__":
    main()