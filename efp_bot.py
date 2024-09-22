import requests
import json
import tweepy
import os
import logging
import time
import random
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
MAX_TWEETS_PER_RUN = 15

# Ethereum-aligned lingo
ETH_INTROS = [
    "🚀 Ether-nauts, buckle up! The @efp gossip machine is hotter than a freshly minted NFT! 🔥",
    "🌠 Cosmic shift in the Ethereum social sphere! @efp's got tea spicier than a failed hard fork! ☕️",
    "🎭 Drama in the decentralized social scene! @efp's dishing out goss faster than Vitalik tweets! 🍿",
    "🌈 Rainbows and unicorns in @efp land! Who's causing more buzz than an ETH2 upgrade? 🦄",
    "💥 ETH socialites making waves! @efp's got the 411 hotter than gas fees on NFT drop day! 🌊"
]

ETH_ACTIONS = {
    "new_user": ["just ape'd into @efp faster than you can say 'gas war'", "emerged from the ETH mist on @efp like a shiny new altcoin", "materialized in the @efp metaverse, ready to farm some social yield"],
    "created_list": ["birthed a shiny new @efp list, bullish on their curation skills!", "conjured up an @efp list from the ether, it's giving 'alpha leak' vibes"],
    "list_change": ["went on an @efp list-creating frenzy, more lists than a DAO has governance proposals", "summoned a bunch of new @efp lists, collecting accounts like they're rare NFTs"],
    "follower_change": ["is attracting ETH whales on @efp like it's ICO season all over again", "just had their @efp follower count go more parabolic than ETH's price chart"],
    "significant_follow": ["just added some ETH royalty to their @efp following, bullish on their networking skills", "is now keeping tabs on the crème de la crème of @efp, major alpha alert!"],
    "unfollow": ["just purged their @efp following faster than a paper hands selling the dip", "went on an @efp unfollowing spree, bear market for their social graph?"],
    "block": ["just deployed some @efp blocks, building walls higher than post-merge gas fees", "fortified their @efp castle walls, no FUD getting through here"],
    "mute": ["hit the magical @efp mute button, silencing more noise than a layer 2 solution", "cast a silence spell on some @efp accounts, peace restored faster than a quick block confirmation"],
    "rank_change": ["just moonshot into the @efp top 20, time to change their Twitter bio?", "leveled up to @efp crypto influencer status, incoming sponsored posts in 3... 2... 1..."],
    "ens_change": ["got a fresh @efp ENS makeover, looking more unique than a rare Cryptopunk", "rebranded their @efp digital identity, bullish on their personal token"],
    "account_change": ["gave their @efp profile a glow-up brighter than the ETH beacon chain", "polished their @efp digital presence, looking more slick than a DEX interface after a UX upgrade"]
}

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
                logging.warning(f"404 Not Found for user {user} at paginated endpoint {endpoint}. Did they rug pull their account?")
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
                logging.info(f"Successfully fetched {endpoint} data for {user}. It's like finding a diamond in the blockchain!")
            except Exception as e:
                logging.error(f"Error fetching {endpoint} for {user}: {e}. Looks like their data is more elusive than a rare NFT!")
                user_data[endpoint] = None

    return user_data if all(user_data.values()) else None

def detect_changes(old_data, new_data):
    changes = []
    
    if old_data is None and new_data is None:
        return changes
    
    if old_data is None:
        changes.append(("new_user", random.choice(ETH_ACTIONS["new_user"])))
        return changes
    
    if new_data is None:
        return changes

    # Check if a list was created for the first time
    old_lists = old_data.get('lists', {}).get('lists', [])
    new_lists = new_data.get('lists', {}).get('lists', [])
    if not old_lists and new_lists:
        changes.append(("created_list", f"{random.choice(ETH_ACTIONS['created_list'])} '{new_lists[0]['name']}'"))
    elif len(new_lists) - len(old_lists) >= LIST_CHANGE_THRESHOLD:
        changes.append(("list_change", f"{random.choice(ETH_ACTIONS['list_change'])} ({len(new_lists) - len(old_lists)} new lists)"))
    
    # Check for significant follower changes
    old_followers = old_data.get('stats', {}).get('followers', 0)
    new_followers = new_data.get('stats', {}).get('followers', 0)
    follower_change = new_followers - old_followers
    if abs(follower_change) >= FOLLOWER_CHANGE_THRESHOLD:
        changes.append(("follower_change", f"{random.choice(ETH_ACTIONS['follower_change'])} ({follower_change:+d} followers)"))
    
    # Check for significant following changes
    old_following = set(f['data'] for f in old_data.get('allFollowing', []))
    new_following = set(f['data'] for f in new_data.get('allFollowing', []))
    followed = new_following - old_following
    unfollowed = old_following - new_following
    
    # Check for significant follows (people from watchlist)
    significant_follows = [user for user in followed if user in WATCHLIST]
    if significant_follows:
        changes.append(("significant_follow", f"{random.choice(ETH_ACTIONS['significant_follow'])} (Added: {', '.join(significant_follows)})"))
    
    # Check for unfollows
    if len(unfollowed) >= FOLLOWING_CHANGE_THRESHOLD:
        changes.append(("unfollow", f"{random.choice(ETH_ACTIONS['unfollow'])} ({len(unfollowed)} accounts)"))
    
    # Check for blocks
    old_blocks = set(f['data'] for f in old_data.get('allFollowing', []) if 'block' in f.get('tags', []))
    new_blocks = set(f['data'] for f in new_data.get('allFollowing', []) if 'block' in f.get('tags', []))
    blocked = new_blocks - old_blocks
    if blocked:
        changes.append(("block", f"{random.choice(ETH_ACTIONS['block'])} ({len(blocked)} accounts)"))
    
    # Check for mutes
    old_mutes = set(f['data'] for f in old_data.get('allFollowing', []) if 'mute' in f.get('tags', []))
    new_mutes = set(f['data'] for f in new_data.get('allFollowing', []) if 'mute' in f.get('tags', []))
    muted = new_mutes - old_mutes
    if muted:
        changes.append(("mute", f"{random.choice(ETH_ACTIONS['mute'])} ({len(muted)} accounts)"))
    
    # Check for rank changes
    old_rank = old_data.get('details', {}).get('ranks', {}).get('mutuals_rank')
    new_rank = new_data.get('details', {}).get('ranks', {}).get('mutuals_rank')
    if old_rank and new_rank and int(old_rank) > 20 and int(new_rank) <= 20:
        changes.append(("rank_change", random.choice(ETH_ACTIONS['rank_change'])))
    
    # Check for ENS changes
    old_ens = old_data.get('ens', {})
    new_ens = new_data.get('ens', {})
    if old_ens != new_ens:
        changes.append(("ens_change", random.choice(ETH_ACTIONS['ens_change'])))

    # Check for account changes
    old_account = old_data.get('account', {})
    new_account = new_data.get('account', {})
    if old_account != new_account:
        changes.append(("account_change", random.choice(ETH_ACTIONS['account_change'])))

    return changes

def post_individual_tweet(tweet):
    try:
        response = twitter_client.create_tweet(text=tweet)
        logging.info(f"Tweet posted successfully! Tweet ID: {response.data['id']}. It's live on the blockchain... err, Twitter!")
        time.sleep(60)  # Wait a minute between tweets to avoid rate limiting
    except Exception as e:
        logging.error(f"Error posting tweet: {e}. Looks like our transaction... err, tweet got rejected!")

def generate_individual_tweets(all_changes):
    tweets = []
    for user, changes in all_changes:
        intro = random.choice(ETH_INTROS)
        action = random.choice([c[1] for c in changes])
        tweet = f"{intro}\n\n🧙‍♂️ {user} {action}\n\nCatch all the @efp action at https://testing.ethfollow.xyz/{user} 🍿"
        tweets.append(tweet[:280])  # Ensure we don't exceed Twitter's character limit
        if len(tweets) == MAX_TWEETS_PER_RUN:
            break
    return tweets

def main():
    start_time = time.time()
    state = load_state()
    
    if not state:
        logging.error("No state loaded. Exiting faster than a panic sell!")
        return

    # Process all users in the state
    users_to_process = list(state.keys())
    
    updated_state = {}
    all_changes = []
    failing_users = set()
    
    for user in tqdm(users_to_process, desc="Stalking ETH accounts"):
        if time.time() - start_time > 800:  # Stop processing after ~13 minutes
            logging.warning("Time limit approaching. Wrapping up the gossip session faster than a quick block confirmation!")
            break
        
        user_start_time = time.time()
        old_data = state[user]
        new_data = get_user_data(user)
        
        if new_data is None:
            logging.warning(f"Failed to fetch data for {user}. They've gone darker than a bear market!")
            failing_users.add(user)
            updated_state[user] = old_data
        else:
            changes = detect_changes(old_data, new_data)
            if changes:
                all_changes.append((user, changes))
                updated_state[user] = new_data
                logging.info(f"Changes detected for {user}: {', '.join([c[1] for c in changes])}. It's like watching a live trading chart!")
            else:
                updated_state[user] = new_data
                logging.info(f"No changes detected for {user}. HODLing steady!")
        
        user_time = time.time() - user_start_time
        logging.info(f"Processed {user} in {user_time:.2f} seconds. Faster than you can say 'gas fees'!")
    
    # Update state for all users
    state.update(updated_state)
    save_state(state)
    
    # Generate and post individual tweets
    if all_changes:
        tweets = generate_individual_tweets(all_changes)
        for tweet in tweets:
            post_individual_tweet(tweet)
    
    total_time = time.time() - start_time
    logging.info(f"Total execution time: {total_time:.2f} seconds. We're faster than a Solana transaction... wait, is that a compliment?")
    logging.info(f"Processed {len(updated_state)} users. That's more accounts than a crypto mixer!")

    if failing_users:
        logging.warning(f"Users with consistently failing data (probably just paper hands): {', '.join(failing_users)}")

if __name__ == "__main__":
    main()