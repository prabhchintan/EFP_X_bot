import tweepy
from dotenv import load_dotenv
import os

load_dotenv()

client = tweepy.Client(
    consumer_key=os.getenv("TWITTER_CONSUMER_KEY"),
    consumer_secret=os.getenv("TWITTER_CONSUMER_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
)

try:
    response = client.create_tweet(text="Ethereum Follow Protocol.")
    print(f"Tweet posted successfully! Tweet ID: {response.data['id']}")
except Exception as e:
    print(f"Error posting tweet: {e}")