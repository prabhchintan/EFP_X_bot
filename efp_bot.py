import requests
import json
import tweepy
import os
import logging
import time
import schedule
from dotenv import load_dotenv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import backoff
from collections import deque

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
MAX_TWEETS_PER_RUN = 15  # Increased from 5 to 15
TWEET_QUEUE_FILE = 'tweet_queue.json'
TWEET_INTERVAL_MINUTES = 20  # Post a tweet every 20 minutes

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

CONFIG = load_config()
WATCHLIST = set(CONFIG['watchlist'])
FOLLOWER_CHANGE_THRESHOLD = CONFIG['significant_follower_change']
FOLLOWING_CHANGE_THRESHOLD = CONFIG['significant_following_change']
LIST_CHANGE_THRESHOLD = CONFIG['significant_list_change']
TAG_CHANGE_THRESHOLD = CONFIG['significant_tag_change']

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

def load_tweet_queue():
    try:
        with open(TWEET_QUEUE_FILE, 'r') as f:
            return deque(json.load(f), maxlen=100)
    except FileNotFoundError:
        return deque(maxlen=100)

def save_tweet_queue(queue):
    with open(TWEET_QUEUE_FILE, 'w') as f:
        json.dump(list(queue), f)

@backoff.on_exception(backoff.expo, requests.RequestException, max_tries=MAX_RETRIES)
def get_endpoint_data(user, endpoint, params=None):
    url = f"{EFP_API_BASE}/users/{user}/{endpoint}"
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def get_paginated_data(user, endpoint):
    all_data = []
    offset = 0
    limit = 100
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
    endpoints = ['details', 'stats', 'lists', 'following', 'ens', 'account', 'allFollowing', 'allFollowers']

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_endpoint = {
            executor.submit(get_endpoint_data, user, endpoint): endpoint 
            for endpoint in endpoints if endpoint not in ['following', 'allFollowing', 'allFollowers']
        }
        future_to_endpoint[executor.submit(get_paginated_data, user, 'following')] = 'following'
        future_to_endpoint[executor.submit(get_paginated_data, user, 'allFollowing')] = 'allFollowing'
        future_to_endpoint[executor.submit(get_paginated_data, user, 'allFollowers')] = 'allFollowers'

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
        changes.append(("new_user", "just joined @efp"))
        return changes
    
    if new_data is None:
        return changes

    # Check if a list was created for the first time
    old_lists = old_data.get('lists', {}).get('lists', [])
    new_lists = new_data.get('lists', {}).get('lists', [])
    if not old_lists and new_lists:
        changes.append(("created_list", f"created their first @efp list '{new_lists[0]['name']}'"))
    elif len(new_lists) - len(old_lists) >= LIST_CHANGE_THRESHOLD:
        changes.append(("list_change", f"created {len(new_lists) - len(old_lists)} new @efp lists"))
    
    # Check for significant follower changes
    old_followers = old_data.get('stats', {}).get('followers', 0)
    new_followers = new_data.get('stats', {}).get('followers', 0)
    follower_change = new_followers - old_followers
    if abs(follower_change) >= FOLLOWER_CHANGE_THRESHOLD:
        changes.append(("follower_change", f"{'gained' if follower_change > 0 else 'lost'} {abs(follower_change)} @efp followers"))
    
    # Check for significant following changes
    old_following = set(f['data'] for f in old_data.get('allFollowing', []))
    new_following = set(f['data'] for f in new_data.get('allFollowing', []))
    followed = new_following - old_following
    unfollowed = old_following - new_following
    
    # Check for significant follows (people from watchlist)
    significant_follows = [user for user in followed if user in WATCHLIST]
    if significant_follows:
        changes.append(("significant_follow", f"started following {', '.join(significant_follows)} on @efp"))
    
    # Check for unfollows
    if len(unfollowed) >= FOLLOWING_CHANGE_THRESHOLD:
        changes.append(("unfollow", f"unfollowed {len(unfollowed)} accounts on @efp"))
    
    # Check for blocks
    old_blocks = set(f['data'] for f in old_data.get('allFollowing', []) if 'block' in f.get('tags', []))
    new_blocks = set(f['data'] for f in new_data.get('allFollowing', []) if 'block' in f.get('tags', []))
    blocked = new_blocks - old_blocks
    if blocked:
        changes.append(("block", f"blocked {len(blocked)} accounts on @efp"))
    
    # Check for mutes
    old_mutes = set(f['data'] for f in old_data.get('allFollowing', []) if 'mute' in f.get('tags', []))
    new_mutes = set(f['data'] for f in new_data.get('allFollowing', []) if 'mute' in f.get('tags', []))
    muted = new_mutes - old_mutes
    if muted:
        changes.append(("mute", f"muted {len(muted)} accounts on @efp"))
    
    # Check for rank changes
    old_rank = old_data.get('details', {}).get('ranks', {}).get('mutuals_rank')
    new_rank = new_data.get('details', {}).get('ranks', {}).get('mutuals_rank')
    if old_rank and new_rank and int(old_rank) > 20 and int(new_rank) <= 20:
        changes.append(("rank_change", f"just entered the top 20 @efp ranks"))
    
    # Check for ENS changes
    old_ens = old_data.get('ens', {})
    new_ens = new_data.get('ens', {})
    if old_ens != new_ens:
        changes.append(("ens_change", "updated their ENS data"))

    # Check for account changes
    old_account = old_data.get('account', {})
    new_account = new_data.get('account', {})
    if old_account != new_account:
        changes.append(("account_change", "refreshed their @efp profile"))

    return changes

def generate_summary_tweet(all_changes):
    if not all_changes:
        return None

    # Sort changes by priority (number of changes) and select the top user
    prioritized_changes = sorted(all_changes, key=lambda x: len(x[1]), reverse=True)
    top_user, top_changes = prioritized_changes[0]

    intro = "🚀 @efp Update Alert! 🚀"
    body = f"{top_user} is making moves: {', '.join([c[1] for c in top_changes[:3]])}"
    
    if len(prioritized_changes) > 1:
        other_users = [user for user, _ in prioritized_changes[1:4]]
        outro = f"Also watch: {', '.join(other_users)}"
    else:
        outro = "Stay tuned for more @efp action! 👀"
    
    tweet = f"{intro}\n\n{body}\n\n{outro}\n\nhttps://testing.ethfollow.xyz/{top_user}"
    
    return tweet[:280]  # Twitter character limit

def post_tweet(message):
    try:
        response = twitter_client.create_tweet(text=message)
        logging.info(f"Tweet posted successfully! Tweet ID: {response.data['id']}")
    except Exception as e:
        logging.error(f"Error posting tweet: {e}")

def calculate_priority(change):
    # Implement a priority calculation based on the type and significance of the change
    # This is a simple example; you may want to adjust based on your specific needs
    priority_map = {
        "new_user": 10,
        "created_list": 8,
        "significant_follow": 7,
        "follower_change": 6,
        "rank_change": 5,
        "list_change": 4,
        "unfollow": 3,
        "block": 2,
        "mute": 1,
        "ens_change": 1,
        "account_change": 1
    }
    return sum(priority_map.get(c[0], 0) for c in change[1])

def staggered_tweet_posting(tweet_queue):
    if tweet_queue:
        tweet = tweet_queue.popleft()
        post_tweet(tweet)
        save_tweet_queue(tweet_queue)
        logging.info(f"Posted tweet. Remaining in queue: {len(tweet_queue)}")

def main():
    start_time = time.time()
    state = load_state()
    tweet_queue = load_tweet_queue()
    
    if not state:
        logging.error("No state loaded. Exiting.")
        return

    # Process all users in the state
    users_to_process = list(state.keys())
    
    updated_state = {}
    all_changes = []
    failing_users = set()
    
    for user in tqdm(users_to_process, desc="Processing users"):
        user_start_time = time.time()
        old_data = state[user]
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
        
        user_time = time.time() - user_start_time
        logging.info(f"Processed {user} in {user_time:.2f} seconds")
    
    # Update state for all users
    state.update(updated_state)
    save_state(state)
    
    # Generate tweets and add to queue
    for user, changes in all_changes:
        tweet = generate_summary_tweet([(user, changes)])
        if tweet:
            tweet_queue.append(tweet)
    
    # Sort tweet queue by priority
    tweet_queue = deque(sorted(tweet_queue, key=lambda x: calculate_priority(x), reverse=True))
    
    # Schedule staggered tweet posting
    for _ in range(min(len(tweet_queue), MAX_TWEETS_PER_RUN)):
        schedule.every(TWEET_INTERVAL_MINUTES).minutes.do(staggered_tweet_posting, tweet_queue)
    
    # Run scheduled tasks for the next few hours
    end_time = time.time() + 7 * 3600  # Run for 7 hours
    while time.time() < end_time:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
    
    save_tweet_queue(tweet_queue)
    
    total_time = time.time() - start_time
    logging.info(f"Total execution time: {total_time:.2f} seconds")
    logging.info(f"Processed {len(users_to_process)} users")
    logging.info(f"Remaining in tweet queue: {len(tweet_queue)}")

    if failing_users:
        logging.warning(f"Users with consistently failing data: {', '.join(failing_users)}")

if __name__ == "__main__":
    main()