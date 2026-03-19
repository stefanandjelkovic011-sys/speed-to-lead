# X Financial Markets Bot

Automated X (Twitter) posting bot for financial markets commentary. Generates data-driven posts about stocks, macro economics, earnings, and market movements using Claude AI with live market data.

## Features

- **8 scheduled posts per day** across market hours (7 AM - 8 PM ET)
- **6 content categories**: market commentary, earnings, big movers, macro, stock ideas, company news
- **Live market data** via yfinance (indices, VIX, yields, sectors, movers)
- **AI-powered content** via Claude claude-sonnet-4-20250514 — no templates, every post is unique
- **Deduplication** — SQLite tracks post history, prevents repetitive content
- **Two posting modes**: Twitter API v2 (tweepy) or Playwright browser (zero API credits)
- **High-volatility detection** — extra posts when VIX > 20
- **Dry run mode** for testing without posting

## Setup

### 1. Create virtual environment

```bash
cd x_bot
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

If using browser mode, also install Playwright browsers:

```bash
playwright install chromium
```

### 3. Get X API Keys

1. Go to [developer.twitter.com](https://developer.twitter.com/en/portal/dashboard)
2. Create a new Project and App
3. Set app permissions to **Read and Write**
4. Generate API Key & Secret, Access Token & Secret, and Bearer Token
5. Copy all 5 values into your `.env` file

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual API keys
```

### 5. Run

```bash
# Test with dry run (prints posts, doesn't send)
python main.py --dry-run --once

# See current market data
python main.py --snapshot

# Run single post
python main.py --once --slot pre_market

# Run production scheduler (8 posts/day)
python main.py
```

## Running in Background

### Using nohup

```bash
nohup python main.py > bot.log 2>&1 &
echo $! > bot.pid  # Save PID for later
```

### Using systemd (Linux)

Create `/etc/systemd/system/x-finance-bot.service`:

```ini
[Unit]
Description=X Financial Markets Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/x_bot
ExecStart=/path/to/x_bot/venv/bin/python main.py
Restart=always
RestartSec=30
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable x-finance-bot
sudo systemctl start x-finance-bot
sudo systemctl status x-finance-bot  # Check status
journalctl -u x-finance-bot -f       # Follow logs
```

## Browser Mode (No API Credits)

Set `USE_BROWSER=true` in `.env` to post via Playwright browser automation instead of the Twitter API. This uses a real browser session and consumes zero API credits.

Requirements:
- `X_USERNAME` and `X_PASSWORD` set in `.env`
- Playwright chromium installed: `playwright install chromium`
- Note: May require handling 2FA if enabled on your account

## Posting Schedule (ET)

| Time | Slot | Content Focus |
|------|------|--------------|
| 7:00 AM | Pre-market | Futures, overnight news |
| 9:35 AM | Market open | Opening reaction |
| 11:00 AM | Momentum | Big movers, momentum |
| 1:00 PM | Midday | Macro/news take |
| 3:00 PM | Power hour | Setups, positioning |
| 4:05 PM | Close recap | End-of-day summary |
| 5:30 PM | After-hours | Earnings reactions |
| 8:00 PM | Evening | Macro thought, preview |

## Disclaimer

All content generated and posted by this bot is **educational commentary only** and does **not** constitute financial advice. The bot does not recommend buying or selling any securities. Market data may be delayed up to 15 minutes. Use at your own risk.
