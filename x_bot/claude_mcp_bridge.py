"""
Claude CLI ↔ Playwright MCP Bridge

This module uses Claude CLI as a subprocess to interact with X (Twitter)
through the Playwright MCP server. Zero API credits consumed.

Flow:
  Bot → claude_mcp_bridge.py → Claude CLI (subprocess) → mcp_server.py → Playwright → X.com

The bridge:
1. Configures Claude CLI to connect to our Playwright MCP server
2. Sends natural language instructions to Claude CLI
3. Claude CLI uses the MCP tools (x_post_tweet, x_reply, etc.) to execute
4. Returns the results back to the bot
"""

import json
import os
import subprocess
import tempfile
from loguru import logger

from config import X_USERNAME, X_PASSWORD


# Path to our MCP server script
MCP_SERVER_PATH = os.path.join(os.path.dirname(__file__), "mcp_server.py")
PYTHON_PATH = os.path.join(os.path.dirname(__file__), "venv", "bin", "python3")

# Fall back to system python if venv doesn't exist
if not os.path.exists(PYTHON_PATH):
    PYTHON_PATH = "python3"


def _get_mcp_config():
    """Generate the MCP server config for Claude CLI."""
    return {
        "mcpServers": {
            "x-playwright": {
                "command": PYTHON_PATH,
                "args": [MCP_SERVER_PATH],
                "env": {
                    "X_USERNAME": X_USERNAME,
                    "X_PASSWORD": X_PASSWORD,
                },
            }
        }
    }


def _write_mcp_config():
    """Write MCP config to a temp file for Claude CLI."""
    config = _get_mcp_config()
    config_path = os.path.join(os.path.dirname(__file__), "data", "mcp_config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    return config_path


def _run_claude_cli(prompt, timeout=120):
    """Run Claude CLI with our MCP server attached.

    Args:
        prompt: natural language instruction for Claude
        timeout: max seconds to wait

    Returns:
        dict with 'success' and 'output' or 'error'
    """
    config_path = _write_mcp_config()

    cmd = [
        "claude",
        "--mcp-config", config_path,
        "-p", prompt,
        "--output-format", "text",
    ]

    logger.debug(f"Running Claude CLI: {' '.join(cmd[:4])}...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(__file__),
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            logger.info(f"Claude CLI success: {output[:100]}...")
            return {"success": True, "output": output}
        else:
            error = result.stderr.strip() or result.stdout.strip()
            logger.error(f"Claude CLI failed: {error[:200]}")
            return {"success": False, "error": error}

    except subprocess.TimeoutExpired:
        logger.error(f"Claude CLI timed out after {timeout}s")
        return {"success": False, "error": "Timed out"}
    except FileNotFoundError:
        logger.error("Claude CLI not found — install with: npm install -g @anthropic-ai/claude-code")
        return {"success": False, "error": "Claude CLI not installed"}


# ─── Public API ──────────────────────────────────────────────────────────────

def post_tweet(text):
    """Post a single tweet via Claude CLI → Playwright MCP.

    Args:
        text: tweet content (max 280 chars)

    Returns:
        dict with success status and tweet_id
    """
    if not X_USERNAME or not X_PASSWORD:
        return {"success": False, "error": "X_USERNAME and X_PASSWORD required in .env"}

    prompt = f"""Use the x_login tool to login with username "{X_USERNAME}" and password "{X_PASSWORD}".
Then use the x_post_tweet tool to post this exact tweet:

{text}

Return the result as JSON."""

    result = _run_claude_cli(prompt, timeout=90)

    if result["success"]:
        return {"success": True, "tweet_id": f"mcp_{hash(text) % 100000}", "output": result["output"]}
    return result


def post_thread(tweets):
    """Post a thread via Claude CLI → Playwright MCP.

    Args:
        tweets: list of tweet strings

    Returns:
        dict with success status and tweet_ids
    """
    if not X_USERNAME or not X_PASSWORD:
        return {"success": False, "error": "X_USERNAME and X_PASSWORD required in .env"}

    tweets_json = json.dumps(tweets)
    prompt = f"""Use the x_login tool to login with username "{X_USERNAME}" and password "{X_PASSWORD}".
Then use the x_post_thread tool with this JSON array of tweets:

{tweets_json}

Return the result as JSON."""

    result = _run_claude_cli(prompt, timeout=120)

    if result["success"]:
        return {"success": True, "tweet_ids": [f"mcp_{i}" for i in range(len(tweets))], "output": result["output"]}
    return result


def reply_to_tweet(tweet_url, text):
    """Reply to a tweet via Claude CLI → Playwright MCP.

    Args:
        tweet_url: URL of the tweet to reply to
        text: reply content (max 280 chars)

    Returns:
        dict with success status
    """
    if not X_USERNAME or not X_PASSWORD:
        return {"success": False, "error": "X_USERNAME and X_PASSWORD required in .env"}

    prompt = f"""Use the x_login tool to login with username "{X_USERNAME}" and password "{X_PASSWORD}".
Then use the x_reply tool to reply to this tweet:
URL: {tweet_url}
Reply text: {text}

Return the result as JSON."""

    return _run_claude_cli(prompt, timeout=90)


def read_timeline(count=10):
    """Read the home timeline via Claude CLI → Playwright MCP.

    Args:
        count: number of tweets to read

    Returns:
        dict with tweets list
    """
    if not X_USERNAME or not X_PASSWORD:
        return {"success": False, "error": "X_USERNAME and X_PASSWORD required in .env"}

    prompt = f"""Use the x_login tool to login with username "{X_USERNAME}" and password "{X_PASSWORD}".
Then use the x_read_timeline tool to read {count} tweets from the home timeline.
Return the tweets as a JSON array with user, text, and url for each."""

    return _run_claude_cli(prompt, timeout=90)


def search_tweets(query, count=10):
    """Search for tweets via Claude CLI → Playwright MCP.

    Args:
        query: search query
        count: max results

    Returns:
        dict with matching tweets
    """
    if not X_USERNAME or not X_PASSWORD:
        return {"success": False, "error": "X_USERNAME and X_PASSWORD required in .env"}

    prompt = f"""Use the x_login tool to login with username "{X_USERNAME}" and password "{X_PASSWORD}".
Then use the x_search tool to search for: {query} (max {count} results).
Return the results as JSON."""

    return _run_claude_cli(prompt, timeout=90)


def get_trending():
    """Get trending topics via Claude CLI → Playwright MCP.

    Returns:
        dict with trending topics list
    """
    if not X_USERNAME or not X_PASSWORD:
        return {"success": False, "error": "X_USERNAME and X_PASSWORD required in .env"}

    prompt = f"""Use the x_login tool to login with username "{X_USERNAME}" and password "{X_PASSWORD}".
Then use the x_get_trending tool to get current trending topics.
Return the trends as a JSON array."""

    return _run_claude_cli(prompt, timeout=90)


def smart_engage(market_snapshot=None):
    """Use Claude CLI to intelligently find and reply to financial tweets.
    Claude reads the timeline, picks the best tweet to engage with,
    generates a data-driven reply, and posts it.

    Args:
        market_snapshot: optional dict of current market data for context

    Returns:
        dict with engagement results
    """
    if not X_USERNAME or not X_PASSWORD:
        return {"success": False, "error": "X_USERNAME and X_PASSWORD required in .env"}

    market_context = ""
    if market_snapshot:
        from prompts import format_snapshot
        market_context = f"\n\nCurrent market data for context:\n{format_snapshot(market_snapshot)}"

    prompt = f"""Use the x_login tool to login with username "{X_USERNAME}" and password "{X_PASSWORD}".

Then do the following:
1. Use x_read_timeline to read the latest 10 tweets
2. Find the most interesting tweet about financial markets, stocks, or economics
3. Generate a sharp, data-driven reply (under 280 chars) that adds value
4. Use x_reply to post your reply to that tweet
{market_context}

Rules for the reply:
- Be analytical and data-driven
- Add new insight, don't just agree
- Keep it under 280 characters
- Tone: confident, professional, occasionally contrarian
- End with "Not financial advice." if it contains an opinion

Return JSON with: original_tweet, your_reply, success status."""

    return _run_claude_cli(prompt, timeout=180)


# ─── Install MCP Server into Claude CLI config ──────────────────────────────

def install_mcp_server():
    """Register the Playwright MCP server with Claude CLI's global config.
    This makes the X tools available in all Claude CLI sessions.
    """
    config_dir = os.path.expanduser("~/.claude")
    os.makedirs(config_dir, exist_ok=True)

    settings_path = os.path.join(config_dir, "settings.json")

    # Load existing settings
    settings = {}
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError:
                settings = {}

    # Add our MCP server
    if "mcpServers" not in settings:
        settings["mcpServers"] = {}

    settings["mcpServers"]["x-playwright"] = {
        "command": PYTHON_PATH,
        "args": [MCP_SERVER_PATH],
    }

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    logger.info(f"Installed x-playwright MCP server into {settings_path}")
    return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "install":
        install_mcp_server()
        print("MCP server registered with Claude CLI.")
        print("You can now use X tools in any Claude CLI session.")
    else:
        print("Claude CLI ↔ Playwright MCP Bridge")
        print()
        print("Usage:")
        print("  python claude_mcp_bridge.py install   # Register MCP with Claude CLI")
        print()
        print("Or import and use in code:")
        print("  from claude_mcp_bridge import post_tweet, reply_to_tweet, smart_engage")
