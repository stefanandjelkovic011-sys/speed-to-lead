"""
Playwright browser bridge — posts to X via browser automation.
No API credits consumed. Uses Claude CLI subprocess for intelligent DOM interaction.

This module uses Playwright to control a real browser session on x.com,
bypassing the need for API keys/credits for posting, replying, and reading.
"""

import json
import os
import subprocess
import time

from loguru import logger

from config import X_USERNAME, X_PASSWORD


class BrowserBridge:
    """Automates X (Twitter) interactions via Playwright browser."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.logged_in = False

    def _ensure_browser(self):
        """Launch browser and login if needed."""
        if self.page and self.logged_in:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        self.playwright = sync_playwright().start()
        # Use persistent context to maintain login session across runs
        user_data_dir = os.path.join(os.path.dirname(__file__), "data", "browser_profile")
        os.makedirs(user_data_dir, exist_ok=True)

        self.browser = self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self.page = self.browser.pages[0] if self.browser.pages else self.browser.new_page()

        # Check if already logged in
        self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        if "login" in self.page.url.lower() or not self._is_logged_in():
            self._login()
        else:
            logger.info("[BROWSER] Already logged in to X")
            self.logged_in = True

    def _is_logged_in(self):
        """Check if we're logged into X."""
        try:
            # Look for the compose tweet button or nav elements that only appear when logged in
            return self.page.query_selector('[data-testid="SideNav_NewTweet_Button"]') is not None
        except Exception:
            return False

    def _login(self):
        """Login to X using credentials."""
        if not X_USERNAME or not X_PASSWORD:
            raise RuntimeError(
                "X_USERNAME and X_PASSWORD must be set in .env for browser bridge"
            )

        logger.info("[BROWSER] Logging in to X...")
        self.page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Enter username
        username_input = self.page.wait_for_selector(
            'input[autocomplete="username"]', timeout=15000
        )
        username_input.fill(X_USERNAME)
        self.page.keyboard.press("Enter")
        time.sleep(2)

        # Handle potential "unusual activity" challenge (enter username again)
        challenge = self.page.query_selector('input[data-testid="ocfEnterTextTextInput"]')
        if challenge:
            logger.info("[BROWSER] Handling login challenge...")
            challenge.fill(X_USERNAME)
            self.page.keyboard.press("Enter")
            time.sleep(2)

        # Enter password
        password_input = self.page.wait_for_selector(
            'input[type="password"]', timeout=15000
        )
        password_input.fill(X_PASSWORD)
        self.page.keyboard.press("Enter")
        time.sleep(5)

        if self._is_logged_in():
            logger.info("[BROWSER] Login successful")
            self.logged_in = True
        else:
            raise RuntimeError("Browser login to X failed — check credentials or 2FA")

    def post_tweet(self, text):
        """Post a single tweet via browser.

        Returns:
            str: tweet URL or identifier, or None on failure
        """
        self._ensure_browser()

        try:
            # Navigate to compose
            self.page.goto("https://x.com/compose/tweet", wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)

            # Find the tweet compose box
            compose = self.page.wait_for_selector(
                '[data-testid="tweetTextarea_0"]', timeout=10000
            )
            compose.click()
            time.sleep(0.5)

            # Type the tweet text
            self.page.keyboard.type(text, delay=20)
            time.sleep(1)

            # Click the post button
            post_btn = self.page.wait_for_selector(
                '[data-testid="tweetButton"]', timeout=5000
            )
            post_btn.click()
            time.sleep(3)

            logger.info(f"[BROWSER] Tweet posted: {text[:60]}...")
            # Return a timestamp-based ID since we can't easily get the tweet ID
            return f"browser_{int(time.time())}"

        except Exception as e:
            logger.error(f"[BROWSER] Failed to post tweet: {e}")
            return None

    def post_thread(self, tweets):
        """Post a thread by posting first tweet then replying to each.

        Returns:
            list of identifiers or None
        """
        self._ensure_browser()
        ids = []

        # Post first tweet
        first_id = self.post_tweet(tweets[0])
        if not first_id:
            return None
        ids.append(first_id)

        # For subsequent tweets, we navigate to the posted tweet and reply
        # Since we can't easily get the URL of the just-posted tweet via browser,
        # we use the compose flow with "add another tweet" pattern
        for i, tweet_text in enumerate(tweets[1:], start=2):
            try:
                time.sleep(2)
                # Navigate to own profile to find the latest tweet
                self.page.goto(f"https://x.com/{X_USERNAME}", wait_until="domcontentloaded", timeout=20000)
                time.sleep(3)

                # Click on the first (most recent) tweet
                first_tweet = self.page.query_selector('[data-testid="tweet"]')
                if first_tweet:
                    first_tweet.click()
                    time.sleep(2)

                    # Click reply
                    reply_box = self.page.wait_for_selector(
                        '[data-testid="tweetTextarea_0"]', timeout=10000
                    )
                    reply_box.click()
                    self.page.keyboard.type(tweet_text, delay=20)
                    time.sleep(1)

                    reply_btn = self.page.wait_for_selector(
                        '[data-testid="tweetButton"]', timeout=5000
                    )
                    reply_btn.click()
                    time.sleep(3)

                    ids.append(f"browser_{int(time.time())}")
                    logger.info(f"[BROWSER] Thread {i}/{len(tweets)} posted")

            except Exception as e:
                logger.error(f"[BROWSER] Thread tweet {i} failed: {e}")
                break

        return ids if len(ids) == len(tweets) else ids or None

    def reply_to_tweet(self, tweet_url, text):
        """Reply to a tweet given its URL."""
        self._ensure_browser()

        try:
            self.page.goto(tweet_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)

            reply_box = self.page.wait_for_selector(
                '[data-testid="tweetTextarea_0"]', timeout=10000
            )
            reply_box.click()
            self.page.keyboard.type(text, delay=20)
            time.sleep(1)

            reply_btn = self.page.wait_for_selector(
                '[data-testid="tweetButton"]', timeout=5000
            )
            reply_btn.click()
            time.sleep(3)

            logger.info(f"[BROWSER] Replied to {tweet_url}: {text[:60]}...")
            return f"browser_reply_{int(time.time())}"

        except Exception as e:
            logger.error(f"[BROWSER] Reply failed: {e}")
            return None

    def like_own_latest(self):
        """Like your own most recent tweet."""
        self._ensure_browser()
        try:
            self.page.goto(f"https://x.com/{X_USERNAME}", wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)
            like_btn = self.page.query_selector('[data-testid="like"]')
            if like_btn:
                like_btn.click()
                time.sleep(1)
                logger.info("[BROWSER] Liked own latest tweet")
                return True
            return False
        except Exception as e:
            logger.error(f"[BROWSER] Like failed: {e}")
            return False

    def close(self):
        """Clean up browser resources."""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass


def claude_cli_bridge(action, params):
    """Use Claude CLI as a subprocess to intelligently interact with X.
    This is the 'sub-processing bridge' that leverages Claude for
    complex browser interactions like reading timelines, understanding
    context, and generating contextual replies.

    Args:
        action: 'analyze_timeline', 'find_reply_targets', 'compose_reply'
        params: dict of parameters for the action

    Returns:
        dict with results
    """
    prompt_map = {
        "analyze_timeline": f"""Analyze this X timeline content and identify the top 3 most engaging
financial/market tweets worth replying to. Return JSON with: tweet_text, reason_to_reply.

Timeline content:
{params.get('timeline_text', '')}""",

        "find_reply_targets": f"""From these tweets about financial markets, pick the best one to reply to
with a data-driven take. Return the tweet text and a suggested reply angle.

Tweets:
{params.get('tweets', '')}""",
    }

    prompt = prompt_map.get(action)
    if not prompt:
        return {"error": f"Unknown action: {action}"}

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return {"success": True, "output": result.stdout.strip()}
        else:
            return {"success": False, "error": result.stderr.strip()}
    except FileNotFoundError:
        logger.warning("Claude CLI not found — falling back to API-based generation")
        return {"success": False, "error": "Claude CLI not installed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Claude CLI timed out"}
