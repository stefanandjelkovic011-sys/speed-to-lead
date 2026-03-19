"""
Claude AI content generation engine.
Generates tweets and threads based on live market data.
"""

import json
import random
from anthropic import Anthropic
from loguru import logger

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CONTENT_CATEGORIES, DB_PATH
from prompts import SYSTEM_PROMPT, build_generation_prompt
from database import get_recent_posts, check_duplicate


client = Anthropic(api_key=ANTHROPIC_API_KEY)


def pick_category(hint=None):
    """Pick a content category based on weights, optionally biased by time hint."""
    if hint and hint in CONTENT_CATEGORIES:
        return hint

    # Weighted random selection
    categories = list(CONTENT_CATEGORIES.keys())
    weights = [CONTENT_CATEGORIES[c]["weight"] for c in categories]
    return random.choices(categories, weights=weights, k=1)[0]


def generate_post(market_snapshot, time_of_day="midday", category_hint=None, max_retries=5):
    """Generate a tweet or thread using Claude.

    Args:
        market_snapshot: dict of current market data
        time_of_day: string describing the posting window
        category_hint: optional category override
        max_retries: max attempts if content fails validation

    Returns:
        dict with keys: content (str or list), category (str), is_thread (bool),
              tickers_mentioned (str)
    """
    category = pick_category(category_hint)
    recent_posts = get_recent_posts(DB_PATH, n=20)

    for attempt in range(max_retries):
        try:
            prompt = build_generation_prompt(
                category=CONTENT_CATEGORIES[category]["label"],
                market_snapshot=market_snapshot,
                recent_posts=recent_posts,
                time_of_day=time_of_day,
            )

            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            logger.debug(f"Claude raw output: {raw[:200]}")

            # Parse response — check if it's a thread (JSON array)
            is_thread = False
            content = raw

            if raw.startswith("["):
                try:
                    thread = json.loads(raw)
                    if isinstance(thread, list) and all(isinstance(t, str) for t in thread):
                        is_thread = True
                        content = thread
                except json.JSONDecodeError:
                    pass  # Not valid JSON, treat as single tweet

            # ─── Validation ───────────────────────────────────────────────
            if is_thread:
                # Validate each tweet in thread
                valid = True
                for i, tweet in enumerate(content):
                    if len(tweet) > 280:
                        logger.warning(f"Thread tweet {i+1} exceeds 280 chars ({len(tweet)}), retrying...")
                        valid = False
                        break
                if not valid:
                    continue
                full_text = " ".join(content)
            else:
                # Strip surrounding quotes if Claude added them
                if content.startswith('"') and content.endswith('"'):
                    content = content[1:-1]

                if len(content) > 280:
                    logger.warning(f"Tweet exceeds 280 chars ({len(content)}), retrying...")
                    continue
                full_text = content

            # Deduplication check
            if check_duplicate(DB_PATH, full_text):
                logger.warning(f"Duplicate detected (attempt {attempt+1}), retrying...")
                continue

            # Extract mentioned tickers
            tickers = _extract_tickers(full_text)

            logger.info(f"Generated {category} post: {full_text[:80]}...")
            return {
                "content": content,
                "category": category,
                "is_thread": is_thread,
                "tickers_mentioned": ",".join(tickers) if tickers else None,
            }

        except Exception as e:
            logger.error(f"Generation attempt {attempt+1} failed: {e}")

    logger.error(f"Failed to generate post after {max_retries} attempts")
    return None


def generate_reply(original_tweet_text, market_snapshot, max_retries=2):
    """Generate a reply to a specific tweet."""
    from prompts import build_reply_prompt

    for attempt in range(max_retries):
        try:
            prompt = build_reply_prompt(original_tweet_text, market_snapshot)

            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            if raw.startswith('"') and raw.endswith('"'):
                raw = raw[1:-1]

            if len(raw) > 280:
                logger.warning(f"Reply exceeds 280 chars, retrying...")
                continue

            return raw

        except Exception as e:
            logger.error(f"Reply generation attempt {attempt+1} failed: {e}")

    return None


def _extract_tickers(text):
    """Extract stock tickers mentioned in text ($ prefixed or known tickers)."""
    import re
    # Find $TICKER patterns
    dollar_tickers = re.findall(r'\$([A-Z]{1,5})\b', text)
    # Find known uppercase ticker patterns
    known = {"SPY", "QQQ", "IWM", "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL",
             "META", "TSLA", "AMD", "INTC", "NFLX", "DIS", "BA", "JPM",
             "GS", "COIN", "PLTR", "SOFI", "UBER"}
    found = [word for word in text.split() if word.upper().strip(".,!?()") in known]
    return list(set(dollar_tickers + [t.upper().strip(".,!?()") for t in found]))
