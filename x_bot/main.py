"""
X Financial Bot — Entry point and scheduler.

Usage:
    python main.py              # Run with scheduler (production)
    python main.py --once       # Generate and post one tweet, then exit
    python main.py --dry-run    # Print without posting
    python main.py --snapshot   # Print current market snapshot and exit
"""

import argparse
import os
import sys

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from loguru import logger

# Setup logging before other imports
LOG_DIR = os.path.join(os.path.dirname(__file__), "data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger.remove()  # Remove default handler
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")
logger.add(
    os.path.join(LOG_DIR, "bot_{time:YYYY-MM-DD}.log"),
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {module}:{function}:{line} | {message}",
)

from config import (
    POST_SCHEDULE, DRY_RUN, USE_MCP, USE_BROWSER, VIX_HIGH_THRESHOLD,
    EXTRA_POSTS_ON_HIGH_VIX, TIME_CATEGORY_MAP, DB_PATH, X_USERNAME,
)
from market_data import get_market_snapshot, get_vix_level
from generator import generate_post, pick_category
from poster import post_tweet, post_thread
from database import get_post_count_today


def _post_actions():
    """After a successful post: like it and open X in the browser."""
    import subprocess

    # Auto-like the post
    try:
        if USE_BROWSER:
            from browser_bridge import BrowserBridge
            bridge = BrowserBridge()
            bridge.like_own_latest()
        elif USE_MCP:
            import claude_mcp_bridge as mcp
            mcp._run_claude_cli(
                f'Use x_login to login as "{X_USERNAME}", then use x_like_tweet to like my most recent tweet.',
                timeout=60,
            )
        logger.info("Auto-liked the post")
    except Exception as e:
        logger.warning(f"Auto-like failed (non-critical): {e}")

    # Open X profile in the system browser
    try:
        profile_url = f"https://x.com/{X_USERNAME}" if X_USERNAME else "https://x.com/home"
        subprocess.run(["open", profile_url], check=False)
        logger.info(f"Opened {profile_url} in browser")
    except Exception as e:
        logger.warning(f"Could not open browser: {e}")


def run_post_job(time_slot="midday"):
    """Execute a single post job: fetch data, generate, post."""
    logger.info(f"═══ Running post job: {time_slot} ═══")

    try:
        # 1. Fetch live market data
        snapshot = get_market_snapshot()
        if not snapshot:
            logger.error("Failed to get market snapshot, skipping post")
            return

        # 2. Determine category from time slot
        category_hint = TIME_CATEGORY_MAP.get(time_slot)

        # 3. Generate content
        result = generate_post(
            market_snapshot=snapshot,
            time_of_day=time_slot,
            category_hint=category_hint,
        )

        if not result:
            logger.error("Content generation failed, skipping post")
            return

        # 4. Post it
        if result["is_thread"]:
            tweet_ids = post_thread(
                result["content"],
                category=result["category"],
                ticker_mentioned=result["tickers_mentioned"],
            )
            if tweet_ids:
                logger.info(f"Thread posted successfully ({len(tweet_ids)} tweets)")
                _post_actions()
        else:
            tweet_id = post_tweet(
                result["content"],
                category=result["category"],
                ticker_mentioned=result["tickers_mentioned"],
            )
            if tweet_id:
                logger.info(f"Tweet posted successfully: {tweet_id}")
                _post_actions()

    except Exception as e:
        logger.exception(f"Post job failed: {e}")


def check_vix_extra_posts():
    """Check VIX level and trigger extra posts on high-volatility days."""
    try:
        vix = get_vix_level()
        if vix and vix > VIX_HIGH_THRESHOLD:
            today_count = get_post_count_today(DB_PATH)
            # Only add extra posts if we haven't already exceeded the expected count
            if today_count < len(POST_SCHEDULE) + EXTRA_POSTS_ON_HIGH_VIX:
                logger.info(f"VIX at {vix} (>{VIX_HIGH_THRESHOLD}), triggering extra post")
                run_post_job(time_slot="high_vol_extra")
    except Exception as e:
        logger.error(f"VIX check failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="X Financial Markets Bot")
    parser.add_argument("--once", action="store_true", help="Post once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print without posting")
    parser.add_argument("--snapshot", action="store_true", help="Print market snapshot and exit")
    parser.add_argument("--slot", type=str, default="midday", help="Time slot for --once mode")
    args = parser.parse_args()

    # Override dry run from CLI
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        import config
        config.DRY_RUN = True
        logger.info("DRY RUN mode enabled")

    # Ensure data directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    logger.info("╔══════════════════════════════════════╗")
    logger.info("║  X Financial Markets Bot             ║")
    logger.info(f"║  Dry Run: {'YES' if DRY_RUN else 'NO':<25s}  ║")
    logger.info("╚══════════════════════════════════════╝")

    if args.snapshot:
        import json
        snapshot = get_market_snapshot()
        print(json.dumps(snapshot, indent=2, default=str))
        return

    if args.once:
        run_post_job(time_slot=args.slot)
        return

    # ─── Production scheduler ─────────────────────────────────────────────
    scheduler = BlockingScheduler(timezone=pytz.timezone("US/Eastern"))

    # Schedule regular posts
    for hour, minute, slot_name in POST_SCHEDULE:
        scheduler.add_job(
            run_post_job,
            CronTrigger(hour=hour, minute=minute, timezone=pytz.timezone("US/Eastern")),
            args=[slot_name],
            id=f"post_{slot_name}",
            name=f"Post: {slot_name} ({hour:02d}:{minute:02d} ET)",
            misfire_grace_time=300,
        )
        logger.info(f"Scheduled: {slot_name} at {hour:02d}:{minute:02d} ET")

    # VIX check every 2 hours during market hours
    scheduler.add_job(
        check_vix_extra_posts,
        CronTrigger(hour="10,12,14", minute=30, timezone=pytz.timezone("US/Eastern")),
        id="vix_check",
        name="VIX high-vol check",
        misfire_grace_time=300,
    )
    logger.info("Scheduled: VIX check at 10:30, 12:30, 14:30 ET")

    logger.info(f"Bot running with {len(POST_SCHEDULE)} scheduled posts per day")
    logger.info("Press Ctrl+C to stop")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down...")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
