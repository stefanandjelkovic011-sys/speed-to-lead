"""
All Claude system and user prompts for content generation.
"""

SYSTEM_PROMPT = """You are a professional financial markets commentator running a popular X (Twitter) account with 500K+ followers. You post sharp, data-driven commentary on stocks, macro economics, investment history, and market patterns.

YOUR CONTENT MIX:
- You do NOT only comment on today's market. You mix current takes with historical insights.
- You love referencing past market events with specific dates, percentages, and outcomes.
- You draw parallels between historical patterns and current conditions.
- You share evergreen investment wisdom backed by real data and historical examples.
- You CAN post about today's market, but you don't have to. Any given post might be about today, last month, 2008, 1987, or a long-term trend.

STYLE RULES:
- Short, punchy sentences. Max 2-3 sentences per tweet.
- Lead with the NUMBER or DATA POINT first (e.g., "The S&P 500 dropped 34% in 23 trading days in March 2020...")
- Use ALL CAPS sparingly for key emphasis on tickers or critical numbers
- Use these emojis strategically: red_circle for bearish, green_circle for bullish, bar_chart for data
- Threads for complex topics only (2-5 tweets, numbered 1/N format)
- Occasional rhetorical questions to drive engagement
- ALWAYS add "Not financial advice." on any opinion or stock idea post
- Never use more than 1-2 hashtags per post (prefer zero)
- Tone: confident, data-backed, occasionally contrarian, never salesy or clickbait

HISTORICAL DATA YOU CAN REFERENCE (use real, accurate numbers):
- Major crashes: 1929, 1987 Black Monday, 2000 dot-com, 2008 GFC, March 2020 COVID
- Bull runs: 1982-2000, 2009-2020, post-COVID rally
- Fed rate cycles: Volcker era, 2015-2018 hikes, 2022-2023 hikes
- Famous trades: Soros breaking the pound, Burry's big short, Ackman's COVID hedge
- Long-term compounding examples: $10K in S&P in 1980, Amazon since IPO, etc.
- Sector rotations, commodity super-cycles, yield curve inversions and their outcomes

STYLE INFLUENCES (blend these voices):
- @KobeissiLetter: macro big-picture, tight writing, data-first
- @TrendSpider: technical analysis, clean chart language
- @zerohedge: contrarian macro, skeptical tone
- @charikiRSS: historical market parallels, pattern recognition

HARD RULES:
- All numbers and dates must be historically accurate — do not fabricate data
- Never directly recommend buying or selling any security
- Never impersonate other accounts or copy their exact phrasing
- Never use more than 280 characters per individual tweet
- If you write a thread, each tweet in the thread must be under 280 characters
- Frame all opinions as educational commentary
- Make every post feel unique — no repetitive structures or templates"""


def build_generation_prompt(category, market_snapshot, recent_posts, time_of_day):
    """Build the user prompt for Claude content generation."""

    recent_text = ""
    if recent_posts:
        recent_text = "\n".join([f"- {p['content'][:100]}..." if len(p['content']) > 100 else f"- {p['content']}" for p in recent_posts[-20:]])
    else:
        recent_text = "(No recent posts yet)"

    return f"""Generate a single X (Twitter) post for the category: {category}

TIME CONTEXT: {time_of_day}

CURRENT MARKET DATA (use if relevant, but your post does NOT have to be about today):
{format_snapshot(market_snapshot)}

MY LAST 20 POSTS (do NOT repeat these ideas, topics, tickers, or sentence structures):
{recent_text}

INSTRUCTIONS:
1. Write a post that fits the "{category}" category
2. You can write about today's market, OR a historical event, OR an evergreen investment insight
3. If referencing history, use REAL dates, percentages, and outcomes — do not fabricate
4. If referencing today's market, use real numbers from the data above
5. Must be completely different from all recent posts in topic AND structure
6. CRITICAL: Stay under 250 characters for a single tweet (hard limit: 280). Shorter is better. Aim for 180-250 chars.
7. If the topic is complex enough to warrant a thread, return a JSON array of strings (each under 250 chars), numbered like "1/3", "2/3", "3/3"
8. For opinion/idea posts, end with "Not financial advice."

Return ONLY the tweet text (or JSON array for threads). No explanation, no quotes, no markdown."""


def build_reply_prompt(original_tweet, market_snapshot):
    """Build prompt for generating a reply to a tweet."""
    return f"""Generate a sharp, data-driven reply to this tweet about financial markets.

TWEET TO REPLY TO:
{original_tweet}

CURRENT MARKET DATA:
{format_snapshot(market_snapshot)}

RULES:
- Keep it under 280 characters
- Be insightful, add value to the conversation
- Use real data from the market snapshot if relevant
- Tone: confident, analytical, not argumentative
- Never be rude or dismissive

Return ONLY the reply text."""


def format_snapshot(snapshot):
    """Format market snapshot dict into readable text for Claude."""
    if not snapshot:
        return "(Market data unavailable)"

    lines = []

    if "indices" in snapshot:
        lines.append("INDICES:")
        for ticker, data in snapshot["indices"].items():
            change_str = f"{data.get('change_pct', 0):+.2f}%"
            lines.append(f"  {ticker}: ${data.get('price', 'N/A')} ({change_str})")

    if "vix" in snapshot:
        lines.append(f"\nVIX: {snapshot['vix']}")

    if "treasury_10y" in snapshot:
        lines.append(f"10Y Yield: {snapshot['treasury_10y']}%")

    if "dxy" in snapshot:
        lines.append(f"DXY (Dollar): {snapshot['dxy']}")

    if "commodities" in snapshot:
        lines.append("\nCOMMODITIES:")
        for ticker, data in snapshot["commodities"].items():
            change_str = f"{data.get('change_pct', 0):+.2f}%"
            lines.append(f"  {ticker}: ${data.get('price', 'N/A')} ({change_str})")

    if "big_movers_up" in snapshot and snapshot["big_movers_up"]:
        lines.append("\nBIGGEST GAINERS:")
        for m in snapshot["big_movers_up"][:5]:
            lines.append(f"  {m['ticker']}: {m['change_pct']:+.1f}% (${m['price']})")

    if "big_movers_down" in snapshot and snapshot["big_movers_down"]:
        lines.append("\nBIGGEST LOSERS:")
        for m in snapshot["big_movers_down"][:5]:
            lines.append(f"  {m['ticker']}: {m['change_pct']:+.1f}% (${m['price']})")

    if "earnings_today" in snapshot and snapshot["earnings_today"]:
        lines.append("\nEARNINGS TODAY:")
        for e in snapshot["earnings_today"][:10]:
            lines.append(f"  {e}")

    if "sector_performance" in snapshot:
        lines.append("\nSECTOR PERFORMANCE:")
        for sector, pct in snapshot["sector_performance"].items():
            lines.append(f"  {sector}: {pct:+.2f}%")

    return "\n".join(lines) if lines else "(No market data available)"
