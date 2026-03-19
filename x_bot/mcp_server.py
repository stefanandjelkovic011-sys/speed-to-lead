#!/usr/bin/env python3
"""
Playwright MCP Server for X (Twitter) — runs as a stdio MCP server.
Claude CLI connects to this server and uses the exposed tools to
post tweets, reply, read timelines, and interact with X.com
without consuming any Twitter API credits.

Protocol: MCP (Model Context Protocol) over stdio (JSON-RPC 2.0)
"""

import json
import os
import sys
import time
import traceback

# ─── MCP Protocol Constants ──────────────────────────────────────────────────
JSONRPC = "2.0"
SERVER_NAME = "x-playwright"
SERVER_VERSION = "1.0.0"

# ─── Global browser state ────────────────────────────────────────────────────
_browser_ctx = None
_page = None
_logged_in = False


def _log(msg):
    """Log to stderr (stdout is reserved for MCP protocol)."""
    sys.stderr.write(f"[mcp-x] {msg}\n")
    sys.stderr.flush()


# ─── Browser Management ─────────────────────────────────────────────────────

def _get_page():
    """Get or create the browser page with persistent login session."""
    global _browser_ctx, _page, _logged_in

    if _page and _logged_in:
        return _page

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")

    if not _browser_ctx:
        pw = sync_playwright().start()
        profile_dir = os.path.join(os.path.dirname(__file__), "data", "mcp_browser_profile")
        os.makedirs(profile_dir, exist_ok=True)

        _browser_ctx = pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=True,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        _page = _browser_ctx.pages[0] if _browser_ctx.pages else _browser_ctx.new_page()

    # Check if already logged in
    _page.goto("https://x.com/home", wait_until="networkidle", timeout=30000)
    time.sleep(3)

    if _page.query_selector('[data-testid="SideNav_NewTweet_Button"]'):
        _logged_in = True
        _log("Already logged in to X")
    else:
        _log("Not logged in — login required via x_login tool")

    return _page


# ─── Tool Implementations ───────────────────────────────────────────────────

def tool_x_login(username, password):
    """Login to X.com with username and password."""
    global _logged_in
    page = _get_page()

    page.goto("https://x.com/i/flow/login", wait_until="networkidle", timeout=30000)
    time.sleep(3)

    # Username
    username_input = page.wait_for_selector('input[autocomplete="username"]', timeout=15000)
    username_input.fill(username)
    page.keyboard.press("Enter")
    time.sleep(2)

    # Handle challenge
    challenge = page.query_selector('input[data-testid="ocfEnterTextTextInput"]')
    if challenge:
        challenge.fill(username)
        page.keyboard.press("Enter")
        time.sleep(2)

    # Password
    password_input = page.wait_for_selector('input[type="password"]', timeout=15000)
    password_input.fill(password)
    page.keyboard.press("Enter")
    time.sleep(5)

    if page.query_selector('[data-testid="SideNav_NewTweet_Button"]'):
        _logged_in = True
        return {"success": True, "message": "Logged in to X successfully"}
    else:
        return {"success": False, "message": "Login failed — check credentials or handle 2FA manually"}


def tool_x_post_tweet(text):
    """Post a single tweet to X."""
    if not _logged_in:
        return {"success": False, "error": "Not logged in. Use x_login first."}
    if len(text) > 280:
        return {"success": False, "error": f"Tweet exceeds 280 chars ({len(text)})"}

    page = _get_page()

    try:
        page.goto("https://x.com/compose/tweet", wait_until="networkidle", timeout=20000)
        time.sleep(2)

        compose = page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=10000)
        compose.click()
        time.sleep(0.5)

        page.keyboard.type(text, delay=15)
        time.sleep(1)

        post_btn = page.wait_for_selector('[data-testid="tweetButton"]', timeout=5000)
        post_btn.click()
        time.sleep(3)

        return {
            "success": True,
            "message": f"Tweet posted: {text[:60]}...",
            "tweet_id": f"browser_{int(time.time())}",
            "chars": len(text),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_x_post_thread(tweets_json):
    """Post a thread (list of tweets). Input is a JSON array of strings."""
    if not _logged_in:
        return {"success": False, "error": "Not logged in. Use x_login first."}

    try:
        tweets = json.loads(tweets_json) if isinstance(tweets_json, str) else tweets_json
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid JSON array for tweets"}

    page = _get_page()
    posted = []

    for i, tweet_text in enumerate(tweets):
        if len(tweet_text) > 280:
            return {"success": False, "error": f"Tweet {i+1} exceeds 280 chars"}

    # Post first tweet
    result = tool_x_post_tweet(tweets[0])
    if not result["success"]:
        return result
    posted.append(result.get("tweet_id"))

    # Reply with subsequent tweets
    for i, tweet_text in enumerate(tweets[1:], start=2):
        try:
            time.sleep(3)
            # Go to profile to find the latest tweet
            page.goto("https://x.com/home", wait_until="networkidle", timeout=20000)
            time.sleep(2)

            # Find the most recent tweet and click it
            first_tweet = page.query_selector('article[data-testid="tweet"]')
            if first_tweet:
                first_tweet.click()
                time.sleep(2)

                reply_box = page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=10000)
                reply_box.click()
                page.keyboard.type(tweet_text, delay=15)
                time.sleep(1)

                reply_btn = page.wait_for_selector('[data-testid="tweetButton"]', timeout=5000)
                reply_btn.click()
                time.sleep(3)

                posted.append(f"browser_{int(time.time())}")
                _log(f"Thread {i}/{len(tweets)} posted")

        except Exception as e:
            return {
                "success": False,
                "error": f"Thread tweet {i} failed: {e}",
                "posted_count": len(posted),
            }

    return {
        "success": True,
        "message": f"Thread posted ({len(posted)} tweets)",
        "tweet_ids": posted,
    }


def tool_x_reply(tweet_url, text):
    """Reply to a specific tweet given its URL."""
    if not _logged_in:
        return {"success": False, "error": "Not logged in. Use x_login first."}
    if len(text) > 280:
        return {"success": False, "error": f"Reply exceeds 280 chars ({len(text)})"}

    page = _get_page()

    try:
        page.goto(tweet_url, wait_until="networkidle", timeout=20000)
        time.sleep(3)

        reply_box = page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=10000)
        reply_box.click()
        page.keyboard.type(text, delay=15)
        time.sleep(1)

        reply_btn = page.wait_for_selector('[data-testid="tweetButton"]', timeout=5000)
        reply_btn.click()
        time.sleep(3)

        return {
            "success": True,
            "message": f"Replied to {tweet_url}",
            "reply_id": f"browser_reply_{int(time.time())}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_x_read_timeline(count=10):
    """Read the latest tweets from the home timeline."""
    if not _logged_in:
        return {"success": False, "error": "Not logged in. Use x_login first."}

    page = _get_page()

    try:
        page.goto("https://x.com/home", wait_until="networkidle", timeout=20000)
        time.sleep(3)

        # Scroll to load tweets
        tweets_data = []
        tweet_elements = page.query_selector_all('article[data-testid="tweet"]')

        for el in tweet_elements[:count]:
            try:
                text_el = el.query_selector('[data-testid="tweetText"]')
                user_el = el.query_selector('[data-testid="User-Name"]')
                tweet_text = text_el.inner_text() if text_el else ""
                user_name = user_el.inner_text().split("\n")[0] if user_el else "Unknown"

                # Try to get the tweet link
                link_el = el.query_selector('a[href*="/status/"]')
                tweet_url = f"https://x.com{link_el.get_attribute('href')}" if link_el else ""

                tweets_data.append({
                    "user": user_name,
                    "text": tweet_text,
                    "url": tweet_url,
                })
            except Exception:
                continue

        return {
            "success": True,
            "tweet_count": len(tweets_data),
            "tweets": tweets_data,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_x_search(query, count=10):
    """Search X for tweets matching a query."""
    if not _logged_in:
        return {"success": False, "error": "Not logged in. Use x_login first."}

    page = _get_page()

    try:
        encoded = query.replace(" ", "%20")
        page.goto(f"https://x.com/search?q={encoded}&f=live", wait_until="networkidle", timeout=20000)
        time.sleep(3)

        tweets_data = []
        tweet_elements = page.query_selector_all('article[data-testid="tweet"]')

        for el in tweet_elements[:count]:
            try:
                text_el = el.query_selector('[data-testid="tweetText"]')
                user_el = el.query_selector('[data-testid="User-Name"]')
                tweet_text = text_el.inner_text() if text_el else ""
                user_name = user_el.inner_text().split("\n")[0] if user_el else "Unknown"

                link_el = el.query_selector('a[href*="/status/"]')
                tweet_url = f"https://x.com{link_el.get_attribute('href')}" if link_el else ""

                tweets_data.append({
                    "user": user_name,
                    "text": tweet_text,
                    "url": tweet_url,
                })
            except Exception:
                continue

        return {
            "success": True,
            "query": query,
            "tweet_count": len(tweets_data),
            "tweets": tweets_data,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_x_like_tweet(tweet_url=""):
    """Like a tweet. If no URL given, likes the most recent tweet on your profile."""
    if not _logged_in:
        return {"success": False, "error": "Not logged in. Use x_login first."}

    page = _get_page()

    try:
        if tweet_url:
            page.goto(tweet_url, wait_until="networkidle", timeout=20000)
        else:
            # Go to own profile and find latest tweet
            page.goto("https://x.com/home", wait_until="networkidle", timeout=20000)
            time.sleep(2)

        time.sleep(2)

        # Find the like button (heart icon)
        like_btn = page.query_selector('[data-testid="like"]')
        if like_btn:
            like_btn.click()
            time.sleep(1)
            return {"success": True, "message": "Tweet liked"}
        else:
            # Already liked?
            unlike_btn = page.query_selector('[data-testid="unlike"]')
            if unlike_btn:
                return {"success": True, "message": "Tweet already liked"}
            return {"success": False, "error": "Like button not found"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_x_get_trending():
    """Get current trending topics on X."""
    if not _logged_in:
        return {"success": False, "error": "Not logged in. Use x_login first."}

    page = _get_page()

    try:
        page.goto("https://x.com/explore/tabs/trending", wait_until="networkidle", timeout=20000)
        time.sleep(3)

        trends = []
        trend_elements = page.query_selector_all('[data-testid="trend"]')
        for el in trend_elements[:20]:
            try:
                text = el.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if lines:
                    trends.append(lines[0] if len(lines) == 1 else lines[1])
            except Exception:
                continue

        return {"success": True, "trends": trends}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── MCP Tool Registry ──────────────────────────────────────────────────────

TOOLS = {
    "x_login": {
        "fn": tool_x_login,
        "description": "Login to X (Twitter) with username and password. Must be called before any other X tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "X username or email"},
                "password": {"type": "string", "description": "X password"},
            },
            "required": ["username", "password"],
        },
    },
    "x_post_tweet": {
        "fn": tool_x_post_tweet,
        "description": "Post a single tweet to X (max 280 characters). No API credits used.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Tweet text (max 280 chars)"},
            },
            "required": ["text"],
        },
    },
    "x_post_thread": {
        "fn": tool_x_post_thread,
        "description": "Post a thread of multiple tweets. Input is a JSON array of tweet strings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tweets_json": {"type": "string", "description": "JSON array of tweet strings"},
            },
            "required": ["tweets_json"],
        },
    },
    "x_reply": {
        "fn": tool_x_reply,
        "description": "Reply to a specific tweet given its URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tweet_url": {"type": "string", "description": "Full URL of the tweet to reply to"},
                "text": {"type": "string", "description": "Reply text (max 280 chars)"},
            },
            "required": ["tweet_url", "text"],
        },
    },
    "x_read_timeline": {
        "fn": tool_x_read_timeline,
        "description": "Read the latest tweets from the home timeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of tweets to read (default 10)", "default": 10},
            },
        },
    },
    "x_search": {
        "fn": tool_x_search,
        "description": "Search X for tweets matching a query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "count": {"type": "integer", "description": "Max results (default 10)", "default": 10},
            },
            "required": ["query"],
        },
    },
    "x_like_tweet": {
        "fn": tool_x_like_tweet,
        "description": "Like a tweet given its URL or the most recent tweet on your profile.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tweet_url": {"type": "string", "description": "Tweet URL to like. If empty, likes your most recent tweet.", "default": ""},
            },
        },
    },
    "x_get_trending": {
        "fn": tool_x_get_trending,
        "description": "Get current trending topics on X.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
}


# ─── MCP Protocol Handler ───────────────────────────────────────────────────

def handle_request(request):
    """Handle a single MCP JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": JSONRPC,
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        }

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    elif method == "tools/list":
        tools_list = []
        for name, spec in TOOLS.items():
            tools_list.append({
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["inputSchema"],
            })
        return {
            "jsonrpc": JSONRPC,
            "id": req_id,
            "result": {"tools": tools_list},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name not in TOOLS:
            return {
                "jsonrpc": JSONRPC,
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                },
            }

        try:
            fn = TOOLS[tool_name]["fn"]
            result = fn(**tool_args)
            return {
                "jsonrpc": JSONRPC,
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "isError": False,
                },
            }
        except Exception as e:
            _log(f"Tool error: {traceback.format_exc()}")
            return {
                "jsonrpc": JSONRPC,
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "isError": True,
                },
            }

    elif method == "ping":
        return {"jsonrpc": JSONRPC, "id": req_id, "result": {}}

    else:
        return {
            "jsonrpc": JSONRPC,
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def main():
    """Run the MCP server on stdio."""
    _log(f"Starting {SERVER_NAME} v{SERVER_VERSION} MCP server on stdio")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _log(f"Invalid JSON: {line[:100]}")
            continue

        response = handle_request(request)

        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
