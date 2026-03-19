"""
X API posting logic — supports both tweepy API v2 and Playwright browser bridge.
"""

import time
from datetime import datetime

import pytz
import tweepy
from loguru import logger

from config import (
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET,
    X_BEARER_TOKEN, DRY_RUN, USE_BROWSER, USE_MCP, QUIET_START, QUIET_END, DB_PATH,
)
from database import save_post


def _is_quiet_hours():
    """Check if we're in quiet hours (11 PM - 6 AM ET)."""
    et = pytz.timezone("US/Eastern")
    now = datetime.now(et)
    return now.hour >= QUIET_START or now.hour < QUIET_END


def _get_tweepy_client():
    """Create authenticated tweepy Client for API v2."""
    return tweepy.Client(
        bearer_token=X_BEARER_TOKEN,
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True,
    )


def post_tweet(text, category="general", ticker_mentioned=None):
    """Post a single tweet.

    Args:
        text: tweet content (must be <= 280 chars)
        category: content category for logging
        ticker_mentioned: comma-separated tickers

    Returns:
        tweet_id (str) or None on failure
    """
    if _is_quiet_hours():
        logger.info("Quiet hours — skipping post")
        return None

    if len(text) > 280:
        logger.error(f"Tweet exceeds 280 chars ({len(text)}), aborting")
        return None

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would post: {text}")
        save_post(DB_PATH, text, category, ticker_mentioned, is_thread=False,
                  tweet_id="dry_run", success=True)
        return "dry_run"

    if USE_MCP:
        return _post_via_mcp(text, category, ticker_mentioned)

    if USE_BROWSER:
        return _post_via_browser(text, category, ticker_mentioned)

    return _post_via_api(text, category, ticker_mentioned)


def post_thread(tweets, category="general", ticker_mentioned=None):
    """Post a thread (list of tweets chained by reply_to).

    Args:
        tweets: list of strings, each <= 280 chars
        category: content category
        ticker_mentioned: comma-separated tickers

    Returns:
        list of tweet_ids or None on failure
    """
    if _is_quiet_hours():
        logger.info("Quiet hours — skipping thread")
        return None

    full_content = " | ".join(tweets)

    if DRY_RUN:
        for i, t in enumerate(tweets):
            logger.info(f"[DRY RUN] Thread {i+1}/{len(tweets)}: {t}")
        save_post(DB_PATH, full_content, category, ticker_mentioned,
                  is_thread=True, tweet_id="dry_run", success=True)
        return ["dry_run"] * len(tweets)

    if USE_MCP:
        return _post_thread_via_mcp(tweets, category, ticker_mentioned)

    if USE_BROWSER:
        return _post_thread_via_browser(tweets, category, ticker_mentioned)

    return _post_thread_via_api(tweets, category, ticker_mentioned)


# ─── API v2 Implementation ────────────────────────────────────────────────────

def _post_via_api(text, category, ticker_mentioned, max_retries=3):
    """Post via tweepy API v2 with retry logic."""
    client = _get_tweepy_client()

    for attempt in range(max_retries):
        try:
            response = client.create_tweet(text=text)
            tweet_id = str(response.data["id"])
            logger.info(f"Posted tweet {tweet_id}: {text[:60]}...")
            save_post(DB_PATH, text, category, ticker_mentioned,
                      is_thread=False, tweet_id=tweet_id, success=True)
            return tweet_id

        except tweepy.TooManyRequests:
            wait = 30 * (attempt + 1)
            logger.warning(f"Rate limited, waiting {wait}s (attempt {attempt+1})")
            time.sleep(wait)

        except tweepy.TwitterServerError as e:
            logger.error(f"Twitter server error: {e}, retrying in 30s...")
            time.sleep(30)

        except Exception as e:
            logger.error(f"Post failed (attempt {attempt+1}): {e}")
            if attempt == max_retries - 1:
                save_post(DB_PATH, text, category, ticker_mentioned,
                          is_thread=False, tweet_id=None, success=False)
            time.sleep(10)

    return None


def _post_thread_via_api(tweets, category, ticker_mentioned):
    """Post a thread via API with reply chaining."""
    client = _get_tweepy_client()
    tweet_ids = []
    reply_to = None

    for i, text in enumerate(tweets):
        try:
            if reply_to:
                response = client.create_tweet(text=text, in_reply_to_tweet_id=reply_to)
            else:
                response = client.create_tweet(text=text)

            tweet_id = str(response.data["id"])
            tweet_ids.append(tweet_id)
            reply_to = tweet_id
            logger.info(f"Thread {i+1}/{len(tweets)} posted: {tweet_id}")
            time.sleep(2)  # Small delay between thread tweets

        except tweepy.TooManyRequests:
            logger.warning("Rate limited during thread, waiting 60s...")
            time.sleep(60)
            # Retry this tweet
            try:
                if reply_to and i > 0:
                    response = client.create_tweet(text=text, in_reply_to_tweet_id=reply_to)
                else:
                    response = client.create_tweet(text=text)
                tweet_id = str(response.data["id"])
                tweet_ids.append(tweet_id)
                reply_to = tweet_id
            except Exception as e:
                logger.error(f"Thread tweet {i+1} failed after retry: {e}")
                break

        except Exception as e:
            logger.error(f"Thread tweet {i+1} failed: {e}")
            break

    full_content = " | ".join(tweets)
    save_post(DB_PATH, full_content, category, ticker_mentioned,
              is_thread=True,
              tweet_id=tweet_ids[0] if tweet_ids else None,
              success=len(tweet_ids) == len(tweets))
    return tweet_ids if tweet_ids else None


# ─── Playwright Browser Bridge ────────────────────────────────────────────────

def _post_via_browser(text, category, ticker_mentioned):
    """Post via Playwright browser automation — no API credits used."""
    try:
        from browser_bridge import BrowserBridge
        bridge = BrowserBridge()
        tweet_id = bridge.post_tweet(text)
        if tweet_id:
            logger.info(f"[BROWSER] Posted: {text[:60]}...")
            save_post(DB_PATH, text, category, ticker_mentioned,
                      is_thread=False, tweet_id=tweet_id, success=True)
        else:
            save_post(DB_PATH, text, category, ticker_mentioned,
                      is_thread=False, tweet_id=None, success=False)
        return tweet_id
    except Exception as e:
        logger.error(f"Browser post failed: {e}")
        save_post(DB_PATH, text, category, ticker_mentioned,
                  is_thread=False, tweet_id=None, success=False)
        return None


def _post_thread_via_browser(tweets, category, ticker_mentioned):
    """Post thread via Playwright browser automation."""
    try:
        from browser_bridge import BrowserBridge
        bridge = BrowserBridge()
        tweet_ids = bridge.post_thread(tweets)
        full_content = " | ".join(tweets)
        save_post(DB_PATH, full_content, category, ticker_mentioned,
                  is_thread=True,
                  tweet_id=tweet_ids[0] if tweet_ids else None,
                  success=bool(tweet_ids))
        return tweet_ids
    except Exception as e:
        logger.error(f"Browser thread failed: {e}")
        full_content = " | ".join(tweets)
        save_post(DB_PATH, full_content, category, ticker_mentioned,
                  is_thread=True, tweet_id=None, success=False)
        return None


# ─── Claude CLI + Playwright MCP Bridge ───────────────────────────────────────

def _post_via_mcp(text, category, ticker_mentioned):
    """Post via Claude CLI → Playwright MCP server — zero API credits."""
    try:
        import claude_mcp_bridge as mcp
        result = mcp.post_tweet(text)
        success = result.get("success", False)
        tweet_id = result.get("tweet_id")
        if success:
            logger.info(f"[MCP] Posted: {text[:60]}...")
        else:
            logger.error(f"[MCP] Post failed: {result.get('error', 'unknown')}")
        save_post(DB_PATH, text, category, ticker_mentioned,
                  is_thread=False, tweet_id=tweet_id, success=success)
        return tweet_id if success else None
    except Exception as e:
        logger.error(f"[MCP] Post failed: {e}")
        save_post(DB_PATH, text, category, ticker_mentioned,
                  is_thread=False, tweet_id=None, success=False)
        return None


def _post_thread_via_mcp(tweets, category, ticker_mentioned):
    """Post thread via Claude CLI → Playwright MCP server."""
    try:
        import claude_mcp_bridge as mcp
        result = mcp.post_thread(tweets)
        success = result.get("success", False)
        tweet_ids = result.get("tweet_ids", [])
        full_content = " | ".join(tweets)
        if success:
            logger.info(f"[MCP] Thread posted ({len(tweets)} tweets)")
        else:
            logger.error(f"[MCP] Thread failed: {result.get('error', 'unknown')}")
        save_post(DB_PATH, full_content, category, ticker_mentioned,
                  is_thread=True,
                  tweet_id=tweet_ids[0] if tweet_ids else None,
                  success=success)
        return tweet_ids if success else None
    except Exception as e:
        logger.error(f"[MCP] Thread failed: {e}")
        full_content = " | ".join(tweets)
        save_post(DB_PATH, full_content, category, ticker_mentioned,
                  is_thread=True, tweet_id=None, success=False)
        return None


def reply_to_tweet(tweet_id, text, category="reply"):
    """Reply to a specific tweet."""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would reply to {tweet_id}: {text}")
        return "dry_run"

    if USE_MCP:
        try:
            import claude_mcp_bridge as mcp
            result = mcp.reply_to_tweet(tweet_id, text)
            return result.get("output") if result.get("success") else None
        except Exception as e:
            logger.error(f"MCP reply failed: {e}")
            return None

    if USE_BROWSER:
        try:
            from browser_bridge import BrowserBridge
            bridge = BrowserBridge()
            return bridge.reply_to_tweet(tweet_id, text)
        except Exception as e:
            logger.error(f"Browser reply failed: {e}")
            return None

    client = _get_tweepy_client()
    try:
        response = client.create_tweet(text=text, in_reply_to_tweet_id=tweet_id)
        reply_id = str(response.data["id"])
        logger.info(f"Replied to {tweet_id} with {reply_id}")
        return reply_id
    except Exception as e:
        logger.error(f"Reply failed: {e}")
        return None
