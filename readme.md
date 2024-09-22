# 🚀 EFP Twitter Bot: The Ethereum Follow Protocol's Biggest Fan! 🐦

Welcome to the coolest bot on the block! This little dynamo is obsessed with the Ethereum Follow Protocol (EFP) leaderboard. It's like a paparazzo for Ethereum accounts, but way less annoying and much more informative!

## 🎭 Features (AKA "The Bot's Superpowers")

- 🕵️‍♂️ Stalks (ahem, "monitors") a customizable list of Ethereum accounts via the EFP API
- 📊 Tracks changes in follower counts, following counts, lists, and tags like a pro statistician
- 🐦 Tweets updates faster than you can say "Ethereum" when big changes happen
- ⏰ Runs every 8 hours using GitHub Actions (because even bots need beauty sleep)
- 🧠 Has a memory better than an elephant, maintaining state between runs

## 🛠 Setup (Don't Worry, It's Easier Than Building IKEA Furniture)

1. Clone this repo (it won't bite, promise!)
2. Install the bot's favorite snacks (dependencies):
   ```
   pip install tweepy requests python-dotenv tqdm schedule
   ```
3. Set up Twitter API credentials (see "Protecting API Keys" section - we're all about that secret agent life)
4. Configure GitHub Actions (see "GitHub Actions Setup" section - it's like training a digital puppy)

## 🏁 Initial State Download (The Bot's First Day at School)

Before your bot can run wild, it needs to learn the basics:

1. Update your `config.json` with all the cool kids (accounts) you want to monitor
2. Run the initial state download script (it's like the bot's first homework assignment):
   ```
   python initial_state_download.py
   ```
3. This creates an `initial_state.json` file (the bot's yearbook of monitored accounts)

## ⚙️ Configuration (Customizing Your Bot's Personality)

The `config.json` file is like your bot's mood ring. It contains:

- `watchlist`: The bot's VIP list of Ethereum accounts to stalk... er, monitor
- `significant_follower_change`: When to get excited about follower count changes
- `significant_following_change`: When to gossip about following count changes
- `significant_list_change`: When to spill the tea about changes in lists
- `significant_tag_change`: When to buzz about changes in tags

## 🔐 Protecting API Keys (Because We're Not About That Public Life)

Keep your API keys secret, keep them safe:

1. Create a `.env` file in your project root (it's like a diary for your bot)
2. Add your Twitter API credentials:
   ```
   TWITTER_CONSUMER_KEY=super_secret_key_here
   TWITTER_CONSUMER_SECRET=even_more_secret_key_here
   TWITTER_ACCESS_TOKEN=top_secret_token_here
   TWITTER_ACCESS_TOKEN_SECRET=ultra_secret_token_here
   ```
3. Add `.env` to your `.gitignore` file (what happens in `.env`, stays in `.env`)

## 🤖 GitHub Actions Setup (Teaching Your Bot to Fly Solo)

1. Go to your GitHub repository settings (it's like the bot's control panel)
2. Navigate to "Secrets and variables" > "Actions" (the bot's secret hideout)
3. Add the Twitter API credentials as secrets (shhh, don't tell anyone)

The `.github/workflows/efp_bot.yml` file is set up to run the bot every 8 hours. It's like having a very punctual, crypto-obsessed cuckoo clock!

## 🎮 Usage (Letting Your Bot Off the Leash)

The bot runs automatically via GitHub Actions, living its best life in the cloud. But if you want to run it locally (maybe it needs a walk?):

```
python efp_bot.py
```

Just make sure you've set the environment variables first. We don't want our bot getting lost!

## 🤝 Contributing (Join the Bot Party!)

Contributions are welcome! Got an idea to make this bot even cooler? Submit a Pull Request and let's make magic happen!

## 📜 License

This project is open source and available under the [MIT License](LICENSE). Use it wisely, and may the force of Ethereum be with you!

Remember, in the world of crypto, this bot's not the hero we deserved, but the hero we needed. Happy monitoring, and may your transactions always be fast and your gas fees low! 🚀🌕