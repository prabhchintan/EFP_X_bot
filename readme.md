# EFP Twitter Bot

## Overview

The EFP Twitter Bot is an automated system designed to monitor and report changes in the Ethereum Follow Protocol (EFP) ecosystem. It tracks a specified list of Ethereum accounts, detects changes in their EFP data, and posts updates to Twitter.

## Features

- Monitors a customizable list of Ethereum accounts via the EFP API
- Tracks changes in follower counts, following counts, lists, and tags
- Detects relationship changes (follows, unfollows, blocks, mutes) between monitored accounts
- Posts updates to Twitter when significant changes occur
- Runs periodically using GitHub Actions
- Maintains state between runs for consistent tracking

## Setup

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up Twitter API credentials (see "Environment Variables" section)
4. Configure GitHub Actions (see "GitHub Actions Setup" section)

## Initial State Download

Before running the bot:

1. Update `config.json` with the list of accounts to monitor
2. Run the initial state download script:
   ```
   python initial_state_download.py
   ```
3. This creates an `initial_state.json` file with the initial data for monitored accounts

## Configuration

The `config.json` file contains:

- `watchlist`: List of Ethereum accounts to monitor
- `check_interval_hours`: Frequency of checks (aligned with GitHub Actions)
- `significant_follower_change`: Threshold for reporting follower count changes
- `significant_following_change`: Threshold for reporting following count changes
- `significant_list_change`: Threshold for reporting changes in lists
- `significant_tag_change`: Threshold for reporting changes in tags

Adjust these values to customize the bot's sensitivity and reporting frequency.

## Environment Variables

Store your API keys securely:

1. Create a `.env` file in the project root
2. Add your Twitter API credentials:
   ```
   TWITTER_CONSUMER_KEY=your_consumer_key
   TWITTER_CONSUMER_SECRET=your_consumer_secret
   TWITTER_ACCESS_TOKEN=your_access_token
   TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret
   ```
3. Add `.env` to your `.gitignore` file

## GitHub Actions Setup

1. Go to your GitHub repository settings
2. Navigate to "Secrets and variables" > "Actions"
3. Add the Twitter API credentials as secrets

The `.github/workflows/efp_bot.yml` file is configured to run the bot periodically.

## Usage

The bot runs automatically via GitHub Actions. To run it locally:

```
python efp_bot.py
```

Ensure environment variables are set before running locally.

## Contributing

Contributions are welcome. Please submit a Pull Request with any enhancements.

## License

This project is open source and available under the [MIT License](LICENSE).