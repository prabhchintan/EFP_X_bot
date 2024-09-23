import requests
import json
import tweepy
import os
import logging
import time
import random
from dotenv import load_dotenv
from tqdm import tqdm
import backoff
from requests.exceptions import Timeout, RequestException
from datetime import datetime

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# EFP API base URL
EFP_API_BASE = "https://testing.ethfollow.xyz/api/v1"
EFP_URL_BASE = "https://testing.ethfollow.xyz"

# Twitter setup
twitter_client = tweepy.Client(
    consumer_key=os.getenv("TWITTER_CONSUMER_KEY"),
    consumer_secret=os.getenv("TWITTER_CONSUMER_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
)

# Constants
MAX_RETRIES = 3

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

CONFIG = load_config()
WATCHLIST = set(CONFIG['watchlist'])

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

def load_tweet_count():
    try:
        with open('tweet_count.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'month': datetime.now().month, 'count': 0}

def save_tweet_count(tweet_count):
    with open('tweet_count.json', 'w') as f:
        json.dump(tweet_count, f)

@backoff.on_exception(backoff.expo, (RequestException, Timeout), max_tries=MAX_RETRIES)
def get_endpoint_data(endpoint, params=None):
    url = f"{EFP_API_BASE}/{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=30)  # 30-second timeout
        response.raise_for_status()
        return response.json()
    except Timeout:
        logging.warning(f"Timeout occurred while fetching {endpoint}")
        raise
    except RequestException as e:
        logging.error(f"Error fetching {endpoint}: {str(e)}")
        raise

def get_paginated_data(endpoint, data_key, params=None, max_pages=10):
    all_data = []
    offset = 0
    limit = 100
    for _ in range(max_pages):
        try:
            params = params or {}
            params.update({'offset': offset, 'limit': limit})
            data = get_endpoint_data(endpoint, params)
            if data_key not in data:
                break
            all_data.extend(data[data_key])
            if len(data[data_key]) < limit:
                break
            offset += limit
        except RequestException:
            break
    return all_data

def get_user_data(user):
    user_data = {}
    try:
        details = get_endpoint_data(f"users/{user}/details")
        user_data['details'] = details
        primary_list_id = details.get('primary_list')
        
        if not primary_list_id:
            logging.warning(f"No primary list found for {user}. Skipping this user.")
            return None

        user_data['stats'] = get_endpoint_data(f"lists/{primary_list_id}/stats")
        user_data['ens'] = get_endpoint_data(f"users/{user}/ens")
        user_data['account'] = get_endpoint_data(f"users/{user}/account")
        user_data['lists'] = get_endpoint_data(f"lists/{primary_list_id}/details")
        user_data['allFollowing'] = get_paginated_data(f"lists/{primary_list_id}/allFollowing", 'following')
        user_data['allFollowers'] = get_paginated_data(f"lists/{primary_list_id}/allFollowers", 'followers')

    except Exception as e:
        logging.error(f"Error fetching data for {user}: {e}")
        return None

    return user_data if all(user_data.values()) else None

def detect_changes(old_data, new_data):
    changes = []
    
    if old_data is None and new_data is None:
        return changes
    
    if old_data is None:
        changes.append(("new_user", "joined @efp"))
        return changes
    
    if new_data is None:
        return changes

    # Check if a list was created for the first time
    old_lists = old_data.get('lists', {}).get('lists', [])
    new_lists = new_data.get('lists', {}).get('lists', [])
    if not old_lists and new_lists:
        changes.append(("created_list", f"created their first @efp list: '{new_lists[0]['name']}'"))
    elif len(new_lists) - len(old_lists) >= CONFIG['tweet_thresholds']['created_list']:
        changes.append(("list_change", f"created {len(new_lists) - len(old_lists)} new @efp lists"))
    
    # Check for significant following changes
    old_following = set(f['data'] for f in old_data.get('allFollowing', []))
    new_following = set(f['data'] for f in new_data.get('allFollowing', []))
    followed = new_following - old_following
    unfollowed = old_following - new_following
    
    # Check for significant follows (people from watchlist)
    significant_follows = [user for user in followed if user in WATCHLIST]
    if significant_follows:
        changes.append(("significant_follow", f"followed {', '.join(significant_follows)} on @efp"))
    
    # Check for unfollows
    if len(unfollowed) >= CONFIG['tweet_thresholds']['unfollow']:
        changes.append(("unfollow", f"unfollowed {len(unfollowed)} accounts on @efp"))
    
    # Check for blocks
    old_blocks = set(f['data'] for f in old_data.get('allFollowing', []) if f.get('is_blocked', False))
    new_blocks = set(f['data'] for f in new_data.get('allFollowing', []) if f.get('is_blocked', False))
    blocked = new_blocks - old_blocks
    if len(blocked) >= CONFIG['tweet_thresholds']['block']:
        changes.append(("block", f"blocked {len(blocked)} accounts on @efp"))
    
    # Check for mutes
    old_mutes = set(f['data'] for f in old_data.get('allFollowing', []) if f.get('is_muted', False))
    new_mutes = set(f['data'] for f in new_data.get('allFollowing', []) if f.get('is_muted', False))
    muted = new_mutes - old_mutes
    if len(muted) >= CONFIG['tweet_thresholds']['mute']:
        changes.append(("mute", f"muted {len(muted)} accounts on @efp"))

    return changes

def get_emoji_for_change_type(change_type):
    emoji_map = {
        'new_user': '👋',
        'created_list': '📋',
        'list_change': '📊',
        'significant_follow': '👥',
        'unfollow': '👋',
        'block': '🚫',
        'mute': '🔇'
    }
    return emoji_map.get(change_type, '')

def can_tweet(tweet_count):
    current_month = datetime.now().month
    if tweet_count['month'] != current_month:
        tweet_count['month'] = current_month
        tweet_count['count'] = 0
    return tweet_count['count'] < CONFIG['max_tweets_per_month']

def post_individual_tweet(tweet, tweet_count):
    if can_tweet(tweet_count):
        try:
            response = twitter_client.create_tweet(text=tweet)
            logging.info(f"Tweet posted successfully! Tweet ID: {response.data['id']}")
            tweet_count['count'] += 1
            save_tweet_count(tweet_count)
            time.sleep(CONFIG['tweet_interval_minutes'] * 60)
        except Exception as e:
            logging.error(f"Error posting tweet: {e}")
    else:
        logging.warning("Monthly tweet limit reached. Skipping tweet.")

def generate_individual_tweets(all_changes):
    tweets = []
    for user, changes in all_changes:
        for change_type, change_details in changes:
            emoji = get_emoji_for_change_type(change_type)
            tweet = f"{emoji} @efp: {user} {change_details}\n\nMore at {EFP_URL_BASE}/{user}"
            tweets.append(tweet[:280])  # Ensure we don't exceed Twitter's character limit
            if len(tweets) == CONFIG['max_tweets_per_run']:
                return tweets
    return tweets

def main():
    start_time = time.time()
    state = load_state()
    tweet_count = load_tweet_count()
    
    if not state:
        logging.error("No state loaded. Exiting.")
        return

    users_to_process = list(state.keys())
    updated_state = {}
    all_changes = []
    failing_users = set()
    
    for user in tqdm(users_to_process, desc="Processing users"):
        try:
            logging.info(f"Starting to process user: {user}")
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
        
        except Exception as e:
            logging.error(f"Unexpected error processing user {user}: {e}")
        
        time.sleep(1)  # Add a short delay between users
    
    state.update(updated_state)
    save_state(state)
    
    if all_changes:
        tweets = generate_individual_tweets(all_changes)
        for tweet in tweets:
            post_individual_tweet(tweet, tweet_count)
    else:
        logging.info("No changes detected for any users")
    
    total_time = time.time() - start_time
    logging.info(f"Total execution time: {total_time:.2f} seconds")
    logging.info(f"Processed {len(updated_state)} users")

    if failing_users:
        logging.warning(f"Users with consistently failing data: {', '.join(failing_users)}")

if __name__ == "__main__":
    main()