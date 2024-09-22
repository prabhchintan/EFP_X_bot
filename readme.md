# EFP Twitter Bot

This project is a Twitter bot that monitors and reports on the Ethereum Follow Protocol (EFP) leaderboard. It fetches data from the EFP API, tracks changes in follower counts, lists, and tags for specified Ethereum accounts, and posts updates to Twitter.

## Features

- Fetches data for a customizable list of Ethereum accounts from the EFP API
- Tracks changes in follower counts, following counts, lists, and tags
- Posts formatted updates to Twitter when significant changes occur
- Runs automatically every 30 minutes using GitHub Actions
- Maintains state between runs to accurately detect changes

## Setup

1. Clone this repository
2. Install required dependencies:
   ```
   pip install tweepy requests python-dotenv tqdm
   ```
3. Set up Twitter API credentials (see "Protecting API Keys" section)
4. Configure GitHub Actions (see "GitHub Actions Setup" section)

## Initial State Download

Before running the bot for the first time, you need to download the initial state:

1. Ensure your `config.json` file is up to date with all the accounts you want to monitor
2. Run the initial state download script:
   ```
   python initial_state_download.py
   ```
3. This will create an `initial_state.json` file with comprehensive data for all monitored accounts
4. Rename `initial_state.json` to `state.json`

## Configuration

The `config.json` file contains the following settings:

- `watchlist`: List of Ethereum accounts to monitor
- `check_interval_minutes`: How often the bot should check for updates
- `significant_follower_change`: Threshold for reporting follower count changes
- `significant_following_change`: Threshold for reporting following count changes
- `significant_list_change`: Threshold for reporting changes in lists
- `significant_tag_change`: Threshold for reporting changes in tags

## Protecting API Keys

To ensure your API keys are not accidentally uploaded to GitHub:

1. Create a file named `.env` in your project root
2. Add your Twitter API credentials to this file:
   ```
   TWITTER_CONSUMER_KEY=your_consumer_key_here
   TWITTER_CONSUMER_SECRET=your_consumer_secret_here
   TWITTER_ACCESS_TOKEN=your_access_token_here
   TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret_here
   ```
3. Add `.env` to your `.gitignore` file

## GitHub Actions Setup

1. Go to your GitHub repository settings
2. Navigate to "Secrets and variables" > "Actions"
3. Add the following secrets:
   - TWITTER_CONSUMER_KEY
   - TWITTER_CONSUMER_SECRET
   - TWITTER_ACCESS_TOKEN
   - TWITTER_ACCESS_TOKEN_SECRET

The `.github/workflows/efp_bot.yml` file is already set up to run the bot every 30 minutes and on manual trigger.

## Usage

The bot is designed to run automatically via GitHub Actions. However, you can also run it locally:

```
python efp_bot.py
```

Make sure to set the required environment variables before running locally.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the [MIT License](LICENSE).