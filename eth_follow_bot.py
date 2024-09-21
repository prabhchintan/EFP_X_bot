import requests
import json
import tweepy
import os
from datetime import datetime

# EFP API base URL
EFP_API_BASE = "https://api.ethfollow.xyz/api/v1"

# Load Twitter configuration from environment variables
twitter_client = tweepy.Client(
    consumer_key=os.environ["TWITTER_CONSUMER_KEY"],
    consumer_secret=os.environ["TWITTER_CONSUMER_SECRET"],
    access_token=os.environ["TWITTER_ACCESS_TOKEN"],
    access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"]
)

# ENS name cache
ens_cache = {}

def get_top_followers(limit=10):
    response = requests.get(f"{EFP_API_BASE}/leaderboard/followers?limit={limit}")
    return response.json()

def get_ens_name(address):
    if address in ens_cache:
        return ens_cache[address]
    
    response = requests.get(f"{EFP_API_BASE}/users/{address}/account")
    data = response.json()
    ens_name = data.get('ens', {}).get('name', address)
    ens_cache[address] = ens_name
    return ens_name

def post_tweet(message):
    try:
        response = twitter_client.create_tweet(text=message)
        print(f"Tweet posted successfully! Tweet ID: {response.data['id']}")
    except Exception as e:
        print(f"Error posting tweet: {e}")

def load_previous_state():
    try:
        with open('previous_state.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_current_state(state):
    with open('previous_state.json', 'w') as f:
        json.dump(state, f)

def create_leaderboard_summary(previous_state):
    top_users = get_top_followers(5)
    current_state = {user['address']: int(user['followers_count']) for user in top_users}
    
    summary = "📊 @efp Follower Leaderboard Update\n\n"
    for i, user in enumerate(top_users):
        ens_name = get_ens_name(user['address'])
        followers = int(user['followers_count'])
        previous_followers = previous_state.get(user['address'], followers)
        
        if followers > previous_followers:
            emoji = "🚀"
        elif followers < previous_followers:
            emoji = "📉"
        else:
            emoji = "➖"
        
        change = followers - previous_followers
        change_text = f"({'+' if change > 0 else ''}{change})" if change != 0 else ""
        
        summary += f"{i+1}. {emoji} {ens_name}: {followers} followers {change_text}\n"
        summary += f"   ethfollow.xyz/{ens_name}\n"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    summary += f"\nUpdated at {timestamp}"
    
    return summary, current_state

def main():
    previous_state = load_previous_state()
    summary, current_state = create_leaderboard_summary(previous_state)
    post_tweet(summary)
    save_current_state(current_state)

if __name__ == "__main__":
    main()