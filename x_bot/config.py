"""
Configuration — post schedule, content categories, tracked tickers.
"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ─── API Keys ────────────────────────────────────────────────────────────────
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ─── X Account Credentials (for Playwright browser bridge) ──────────────────
X_USERNAME = os.getenv("X_USERNAME", "")
X_PASSWORD = os.getenv("X_PASSWORD", "")

# ─── Mode ────────────────────────────────────────────────────────────────────
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
USE_BROWSER = os.getenv("USE_BROWSER", "false").lower() == "true"
USE_MCP = os.getenv("USE_MCP", "false").lower() == "true"  # Claude CLI + Playwright MCP

# ─── Claude Model ────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# ─── Database ────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "posts.db")

# ─── Posting Schedule (ET) ───────────────────────────────────────────────────
# Each entry: (hour, minute, category_hint)
POST_SCHEDULE = [
    (9, 35, "morning"),         # Morning post — market take or historical insight
    (13, 0, "afternoon"),       # Afternoon — macro, historical lesson, or idea
    (16, 5, "evening"),         # Evening — recap, evergreen idea, or contrarian take
]

# Quiet hours — no posts between these times (ET)
QUIET_START = 23  # 11 PM
QUIET_END = 6     # 6 AM

# ─── Content Categories & Weights ────────────────────────────────────────────
CONTENT_CATEGORIES = {
    "market_commentary": {
        "weight": 15,
        "label": "Market Commentary",
        "description": "S&P 500, Nasdaq, Dow moves, VIX, breadth, sector rotation — today or recent",
    },
    "historical_lesson": {
        "weight": 25,
        "label": "Historical Lesson",
        "description": "Past market events, crashes, rallies, patterns that repeated. Reference specific dates, % moves, and what happened next. E.g. 'In March 2020, the S&P dropped 34% in 23 days. 12 months later it was up 75%.' Use real historical data.",
    },
    "investment_idea": {
        "weight": 20,
        "label": "Investment Idea / Thesis",
        "description": "Evergreen investment concepts, sector theses, value vs growth debates, compounding math, risk management. Use historical charts/data as evidence. Not time-sensitive.",
    },
    "macro": {
        "weight": 15,
        "label": "Macro / Economic Insight",
        "description": "Fed policy history, interest rate cycles, inflation patterns, yield curve inversions, dollar strength periods. Can reference current OR historical macro data.",
    },
    "contrarian_take": {
        "weight": 15,
        "label": "Contrarian Take",
        "description": "Challenge popular narratives using historical precedent. 'Everyone thinks X, but historically Y happened.' Data-backed skepticism.",
    },
    "stock_spotlight": {
        "weight": 10,
        "label": "Stock Spotlight",
        "description": "Deep look at one company — historical performance, key turning points, what drove multi-year returns. Educational, not a buy/sell recommendation.",
    },
}

# Time-of-day to category mapping hints (None = weighted random pick)
TIME_CATEGORY_MAP = {
    "morning": None,       # Random from all categories
    "afternoon": None,     # Random from all categories
    "evening": None,       # Random from all categories
}

# ─── Tracked Tickers ─────────────────────────────────────────────────────────
INDEX_TICKERS = ["^GSPC", "^IXIC", "^DJI", "^VIX", "^TNX"]
ETF_TICKERS = ["SPY", "QQQ", "IWM", "DIA"]
COMMODITY_TICKERS = ["GLD", "SLV", "USO", "BTC-USD", "ETH-USD"]
CURRENCY_TICKERS = ["DX-Y.NYB"]  # DXY
SCAN_TICKERS_COUNT = 50  # How many top-volume stocks to scan for movers

# VIX threshold for extra posts
VIX_HIGH_THRESHOLD = 20
EXTRA_POSTS_ON_HIGH_VIX = 2
