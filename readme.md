# EFP Twitter Bot

This project is a Twitter bot that monitors and reports on the Ethereum Follow Protocol (EFP) leaderboard. It fetches data from the EFP API, tracks changes in follower counts for top accounts, and posts updates to Twitter.

## Features

- Fetches the top 5 accounts from the EFP follower leaderboard
- Resolves Ethereum addresses to ENS names when available
- Tracks changes in follower counts between updates
- Posts formatted updates to Twitter, including links to EFP profiles
- Runs automatically every 30 minutes using GitHub Actions

## Setup

1. Clone this repository
2. Install required dependencies:
   ```
   pip install tweepy requests
   ```
3. Set up Twitter API credentials (see "Protecting API Keys" section)
4. Configure GitHub Actions (see "GitHub Actions Setup" section)

## Protecting API Keys

To ensure your API keys are not accidentally uploaded to GitHub:

1. Create a file named `.gitignore` in your project root if it doesn't exist already
2. Add the following lines to `.gitignore`:
   ```
   config.json
   .env
   ```
3. Instead of using a `config.json` file, use environment variables or GitHub Secrets for storing sensitive information

## GitHub Actions Setup

1. Go to your GitHub repository settings
2. Navigate to "Secrets and variables" > "Actions"
3. Add the following secrets:
   - TWITTER_CONSUMER_KEY
   - TWITTER_CONSUMER_SECRET
   - TWITTER_ACCESS_TOKEN
   - TWITTER_ACCESS_TOKEN_SECRET

## Usage

The bot is designed to run automatically via GitHub Actions. However, you can also run it locally:

Make sure to set the required environment variables before running locally.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the [MIT License](LICENSE).