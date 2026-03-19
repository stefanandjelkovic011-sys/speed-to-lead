"""
Live market data fetching via yfinance.
Returns structured snapshots for Claude context.
"""

import yfinance as yf
from loguru import logger


# ─── Sector ETFs for performance tracking ────────────────────────────────────
SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Energy": "XLE",
    "Consumer Disc.": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Comm. Services": "XLC",
}

# Top 50 most-traded US stocks for mover scanning
SCAN_UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "MA", "HD", "PG", "JNJ", "ABBV", "MRK", "AVGO",
    "COST", "PEP", "KO", "WMT", "LLY", "TMO", "ADBE", "CRM", "NFLX",
    "AMD", "INTC", "CSCO", "CMCSA", "PFE", "ABT", "NKE", "DIS", "VZ",
    "T", "PYPL", "BA", "GE", "CAT", "GS", "MS", "AXP", "SCHW",
    "UBER", "SQ", "COIN", "PLTR", "SOFI",
]


def _safe_fetch(ticker_symbol, period="1d", interval="1d"):
    """Safely fetch ticker data, returning None on failure."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        prev_close = hist.iloc[-2]["Close"] if len(hist) > 1 else latest["Open"]
        price = round(latest["Close"], 2)
        change = round(price - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
        return {
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "volume": int(latest.get("Volume", 0)),
        }
    except Exception as e:
        logger.warning(f"Failed to fetch {ticker_symbol}: {e}")
        return None


def get_market_snapshot():
    """Build a comprehensive market data snapshot dict for Claude context."""
    logger.info("Fetching market snapshot...")
    snapshot = {}

    # ─── Major indices ────────────────────────────────────────────────────
    indices = {}
    index_map = {
        "^GSPC": "S&P 500",
        "^IXIC": "Nasdaq",
        "^DJI": "Dow Jones",
    }
    for symbol, name in index_map.items():
        data = _safe_fetch(symbol, period="5d")
        if data:
            indices[name] = data
    snapshot["indices"] = indices

    # ─── VIX ──────────────────────────────────────────────────────────────
    vix_data = _safe_fetch("^VIX", period="5d")
    if vix_data:
        snapshot["vix"] = vix_data["price"]
    else:
        snapshot["vix"] = None

    # ─── 10Y Treasury yield ───────────────────────────────────────────────
    tnx_data = _safe_fetch("^TNX", period="5d")
    if tnx_data:
        snapshot["treasury_10y"] = tnx_data["price"]
    else:
        snapshot["treasury_10y"] = None

    # ─── DXY (US Dollar Index) ────────────────────────────────────────────
    dxy_data = _safe_fetch("DX-Y.NYB", period="5d")
    if dxy_data:
        snapshot["dxy"] = dxy_data["price"]
    else:
        snapshot["dxy"] = None

    # ─── Commodities & crypto ─────────────────────────────────────────────
    commodities = {}
    commodity_map = {
        "GLD": "Gold (GLD)",
        "USO": "Oil (USO)",
        "BTC-USD": "Bitcoin",
        "ETH-USD": "Ethereum",
    }
    for symbol, name in commodity_map.items():
        data = _safe_fetch(symbol, period="5d")
        if data:
            commodities[name] = data
    snapshot["commodities"] = commodities

    # ─── Sector performance ───────────────────────────────────────────────
    sector_perf = {}
    for sector_name, etf in SECTOR_ETFS.items():
        data = _safe_fetch(etf, period="5d")
        if data:
            sector_perf[sector_name] = data["change_pct"]
    snapshot["sector_performance"] = sector_perf

    # ─── Big movers (scan top stocks) ─────────────────────────────────────
    movers = []
    for symbol in SCAN_UNIVERSE:
        data = _safe_fetch(symbol, period="5d")
        if data and abs(data["change_pct"]) >= 2.0:
            movers.append({"ticker": symbol, **data})

    movers_up = sorted([m for m in movers if m["change_pct"] > 0],
                       key=lambda x: x["change_pct"], reverse=True)
    movers_down = sorted([m for m in movers if m["change_pct"] < 0],
                         key=lambda x: x["change_pct"])
    snapshot["big_movers_up"] = movers_up[:5]
    snapshot["big_movers_down"] = movers_down[:5]

    # ─── Earnings calendar (today) ────────────────────────────────────────
    snapshot["earnings_today"] = _get_earnings_today()

    logger.info(f"Market snapshot complete: {len(indices)} indices, "
                f"{len(movers_up)} gainers, {len(movers_down)} losers")
    return snapshot


def _get_earnings_today():
    """Get list of companies reporting earnings today/tomorrow."""
    try:
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Use yfinance earnings calendar — scan our universe
        earnings = []
        for symbol in SCAN_UNIVERSE[:30]:  # Limit to top 30 to save time
            try:
                ticker = yf.Ticker(symbol)
                cal = ticker.calendar
                if cal is not None and not cal.empty if hasattr(cal, 'empty') else cal:
                    if isinstance(cal, dict) and "Earnings Date" in cal:
                        earn_date = str(cal["Earnings Date"])
                        if today in earn_date or tomorrow in earn_date:
                            earnings.append(f"{symbol} (reporting)")
            except Exception:
                continue
        return earnings
    except Exception as e:
        logger.warning(f"Failed to fetch earnings calendar: {e}")
        return []


def get_vix_level():
    """Quick fetch of current VIX level."""
    data = _safe_fetch("^VIX", period="5d")
    return data["price"] if data else None
