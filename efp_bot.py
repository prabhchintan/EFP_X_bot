import requests
import json
import tweepy
import os
import logging
import time
import glob
from dotenv import load_dotenv
from requests.exceptions import Timeout, RequestException
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

# Constants
EFP_API_BASE = "https://api.ethfollow.xyz/api/v1"
EFP_URL_BASE = "https://ethfollow.xyz"
MAX_WORKERS = 10
RATE_LIMIT_DELAY = 1
MAX_TWEETS_PER_HOUR = 100  # Twitter's rate limit

# Twitter setup
twitter_client = tweepy.Client(
    consumer_key=os.getenv("TWITTER_CONSUMER_KEY"),
    consumer_secret=os.getenv("TWITTER_CONSUMER_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
)

def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON in config.json: {e}")
        return None
    except FileNotFoundError:
        logging.error("config.json not found")
        return None

CONFIG = load_config()
if CONFIG is None:
    raise SystemExit("Failed to load configuration. Exiting.")
WATCHLIST = set(CONFIG['watchlist'])

def load_state():
    if os.path.exists('initial_state.json') and os.path.getsize('initial_state.json') > 0:
        with open('initial_state.json', 'r') as f:
            return json.load(f)
    else:
        files = glob.glob('initial_state_*.json')
        if not files:
            logging.error("No initial state file found")
            return None
        latest_file = max(files, key=os.path.getctime)
        logging.warning(f"initial_state.json is empty or doesn't exist. Loading from {latest_file}")
        with open(latest_file, 'r') as f:
            state = json.load(f)
        with open('initial_state.json', 'w') as f:
            json.dump(state, f, indent=2)
        logging.info("Updated initial_state.json with the latest timestamped state")
        return state

def save_state(state):
    try:
        with open('initial_state.json', 'w') as f:
            json.dump(state, f, indent=2)
        logging.info(f"State saved to initial_state.json. File size: {os.path.getsize('initial_state.json')} bytes")
        
        with open('initial_state.json', 'r') as f:
            saved_state = json.load(f)
        if saved_state != state:
            logging.error("Saved state does not match the original state!")
    except Exception as e:
        logging.error(f"Error saving state: {str(e)}")

def get_endpoint_data(endpoint, params=None, timeout=300):  # Increased timeout to 300 seconds
    url = f"{EFP_API_BASE}/{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code == 404:
            logging.warning(f"Endpoint not found: {endpoint}")
            return None
        response.raise_for_status()
        time.sleep(RATE_LIMIT_DELAY)
        return response.json()
    except Timeout:
        logging.warning(f"Timeout occurred while fetching {endpoint}")
    except RequestException as e:
        logging.error(f"Error fetching {endpoint}: {str(e)}")
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for {endpoint}: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error for {endpoint}: {str(e)}")
    return None

def get_paginated_data(endpoint, params=None):
    all_data = []
    offset = 0
    limit = 100
    while True:
        current_params = {'offset': offset, 'limit': limit}
        if params:
            current_params.update(params)
        data = get_endpoint_data(endpoint, params=current_params)
        if data is None:
            break
        new_data = data.get(endpoint.split('/')[-1], [])
        all_data.extend(new_data)
        if len(new_data) < limit:
            break
        offset += limit
    return all_data

def check_active_list(user):
    details = get_endpoint_data(f"users/{user}/details")
    if details and 'primary_list' in details:
        stats = get_endpoint_data(f"lists/{details['primary_list']}/stats")
        return stats and stats.get('following_count', 0) > 0, details['primary_list']
    return False, None

def get_user_data(user, fetch_detailed=False):
    user_data = {}
    try:
        has_active_list, list_id = check_active_list(user)
        user_data['has_profile'] = bool(list_id)
        user_data['list_id'] = list_id
        user_data['has_active_list'] = has_active_list

        # Always fetch basic data, even for inactive profiles
        user_data['details'] = get_endpoint_data(f"users/{user}/details")
        user_data['stats'] = get_endpoint_data(f"users/{user}/stats")
        user_data['ens'] = get_endpoint_data(f"users/{user}/ens")

        if fetch_detailed:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(get_paginated_data, f"users/{user}/followers"): 'followers',
                    executor.submit(get_paginated_data, f"users/{user}/following"): 'following',
                    executor.submit(get_endpoint_data, f"users/{user}/tags"): 'tags'
                }
                
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        data = future.result()
                        if data is not None:
                            user_data[key] = data
                            logging.info(f"Successfully fetched {key} data for {user}. Data size: {len(str(data))} characters")
                        else:
                            logging.warning(f"Failed to fetch {key} data for {user}")
                    except Exception as e:
                        logging.error(f"Error fetching {key} data for {user}: {str(e)}")

        return user_data
    except Exception as e:
        logging.error(f"Error processing data for {user}: {str(e)}")
        return None
    
def get_button_state(list_id, address):
    endpoint = f"lists/{list_id}/{address}/buttonState"
    return get_endpoint_data(endpoint)

def detect_changes(old_data, new_data):
    changes = []
    
    if old_data is None or new_data is None:
        return changes

    # Check for profile activation
    if not old_data.get('has_profile', False) and new_data.get('has_profile', False):
        changes.append(("profile_activation", "activated their profile"))

    old_followers = old_data.get('stats', {}).get('followers_count', 0)
    new_followers = new_data.get('stats', {}).get('followers_count', 0)
    follower_change = int(new_followers) - int(old_followers)
    if abs(follower_change) >= CONFIG['significant_follower_change']:
        changes.append(("follower_change", f"{'gained' if follower_change > 0 else 'lost'} {abs(follower_change)} followers"))

    old_following = old_data.get('stats', {}).get('following_count', 0)
    new_following = new_data.get('stats', {}).get('following_count', 0)
    following_change = int(new_following) - int(old_following)
    if abs(following_change) >= CONFIG['significant_following_change']:
        changes.append(("following_change", f"{'started following' if following_change > 0 else 'unfollowed'} {abs(following_change)} accounts"))

    return changes

def detect_relationship_changes(old_data, new_data, other_users):
    changes = []
    if not new_data.get('list_id'):
        return changes

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for other_user in other_users:
            if other_user == new_data['details']['address']:
                continue
            if old_data and old_data.get('list_id'):
                futures[executor.submit(get_button_state, old_data['list_id'], other_user)] = ('old', other_user)
            futures[executor.submit(get_button_state, new_data['list_id'], other_user)] = ('new', other_user)

        button_states = {}
        for future in as_completed(futures):
            state_type, other_user = futures[future]
            try:
                button_states[(state_type, other_user)] = future.result()
            except Exception as e:
                logging.error(f"Error fetching button state for {other_user}: {str(e)}")

    for other_user in other_users:
        if other_user == new_data['details']['address']:
            continue
        old_state = button_states.get(('old', other_user), {'state': {'follow': False, 'block': False, 'mute': False}})
        new_state = button_states.get(('new', other_user))
        
        if new_state and old_state != new_state:
            if new_state['state']['follow'] and not old_state['state']['follow']:
                changes.append(("new_follow", f"started following {other_user}"))
            elif not new_state['state']['follow'] and old_state['state']['follow']:
                changes.append(("unfollow", f"unfollowed {other_user}"))
            if new_state['state']['block'] and not old_state['state']['block']:
                changes.append(("block", f"blocked {other_user}"))
            elif not new_state['state']['block'] and old_state['state']['block']:
                changes.append(("unblock", f"unblocked {other_user}"))
            if new_state['state']['mute'] and not old_state['state']['mute']:
                changes.append(("mute", f"muted {other_user}"))
            elif not new_state['state']['mute'] and old_state['state']['mute']:
                changes.append(("unmute", f"unmuted {other_user}"))

    return changes

def get_emoji_for_change_type(change_type):
    emoji_map = {
        'profile_activation': '🎉',
        'follower_change': '📈',
        'following_change': '👥',
        'unfollow': '➖',
        'new_follow': '➕',
        'block': '🚫',
        'unblock': '✅',
        'mute': '🔇',
        'unmute': '🔊'
    }
    return emoji_map.get(change_type, '')

def post_tweet(tweet):
    try:
        response = twitter_client.create_tweet(text=tweet)
        logging.info(f"Tweet posted successfully! Tweet ID: {response.data['id']}")
    except Exception as e:
        logging.error(f"Error posting tweet: {e}")

def generate_tweet(changes):
    if not changes:
        return None
    
    user = changes[0][1]  # Get the user from the first change
    tweet = f"{user}:\n"
    
    follow_count = 0
    unfollow_count = 0
    block_count = 0
    unblock_count = 0
    mute_count = 0
    unmute_count = 0
    
    for emoji, _, change in changes:
        if "started following" in change:
            if "accounts" not in change:
                tweet += f"{emoji} {change}\n"
            else:
                follow_count += int(change.split()[2])
        elif "unfollowed" in change:
            if "accounts" not in change:
                tweet += f"➖ {change}\n"
            else:
                unfollow_count += int(change.split()[1])
        elif "blocked" in change:
            block_count += 1
        elif "unblocked" in change:
            unblock_count += 1
        elif "muted" in change:
            mute_count += 1
        elif "unmuted" in change:
            unmute_count += 1
        else:
            tweet += f"{emoji} {change}\n"
    
    if follow_count > 0:
        tweet += f"➕ Started following {follow_count} accounts\n"
    if unfollow_count > 0:
        tweet += f"➖ Unfollowed {unfollow_count} accounts\n"
    if block_count > 0:
        tweet += f"🚫 Blocked {block_count} accounts\n"
    if unblock_count > 0:
        tweet += f"✅ Unblocked {unblock_count} accounts\n"
    if mute_count > 0:
        tweet += f"🔇 Muted {mute_count} accounts\n"
    if unmute_count > 0:
        tweet += f"🔊 Unmuted {unmute_count} accounts\n"
    
    tweet += f"{EFP_URL_BASE}/{user}"
    
    if len(tweet) + 6 <= 280:
        tweet += " @efp"
    
    return tweet[:280].strip()

def main():
    start_time = time.time()
    state = load_state()
    
    if not state:
        logging.error("No state loaded. Exiting.")
        return

    updated_state = {}
    all_changes = []
    failing_users = set()
    tweet_count = 0
    
    for user in tqdm(WATCHLIST, desc="Processing users"):
        try:
            logging.info(f"Starting to process user: {user}")
            user_start_time = time.time()
            old_data = state.get(user)
            new_data = get_user_data(user, fetch_detailed=True)
            
            if new_data is None:
                logging.warning(f"Failed to fetch data for {user}")
                failing_users.add(user)
                updated_state[user] = old_data
            else:
                changes = detect_changes(old_data, new_data)
                if new_data.get('has_profile', False):
                    relationship_changes = detect_relationship_changes(old_data, new_data, WATCHLIST)
                    changes.extend(relationship_changes)
                
                if changes:
                    user_changes = [(get_emoji_for_change_type(c[0]), user, c[1]) for c in changes]
                    all_changes.extend(user_changes)
                    updated_state[user] = new_data
                    logging.info(f"Changes detected for {user}: {', '.join([c[1] for c in changes])}")
                    
                    # Generate and post tweet for this user
                    if tweet_count < MAX_TWEETS_PER_HOUR:
                        tweet = generate_tweet(user_changes)
                        if tweet:
                            post_tweet(tweet)
                            tweet_count += 1
                            time.sleep(60)  # 1-minute delay between tweets
                    else:
                        logging.warning("Reached Twitter rate limit. Stopping tweet posting.")
                else:
                    updated_state[user] = new_data
                    logging.info(f"No changes detected for {user}")
            
            user_time = time.time() - user_start_time
            logging.info(f"Processed {user} in {user_time:.2f} seconds")
        
        except Exception as e:
            logging.error(f"Unexpected error processing user {user}: {e}")
            failing_users.add(user)
        
        # Save state after each user
        state.update(updated_state)
        save_state(state)
        
        # Add a delay between processing users
        time.sleep(30)  # 30-second delay between users
    
    total_time = time.time() - start_time
    logging.info(f"Total execution time: {total_time:.2f} seconds")
    logging.info(f"Total users in watchlist: {len(WATCHLIST)}")
    logging.info(f"Users with consistently failing data: {len(failing_users)}")
    logging.info(f"Total changes detected: {len(all_changes)}")
    logging.info(f"Total tweets posted: {tweet_count}")

    if failing_users:
        logging.warning(f"Users with consistently failing data: {', '.join(failing_users)}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"Critical error in main execution: {e}", exc_info=True)