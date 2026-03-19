"""
SQLite post history, deduplication, and market snapshot logging.
"""

import json
import os
import sqlite3
from datetime import datetime


def get_db(db_path):
    """Get a database connection, creating tables if needed."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT NOT NULL,
            posted_at TEXT DEFAULT (datetime('now')),
            engagement_score INTEGER,
            ticker_mentioned TEXT,
            is_thread INTEGER DEFAULT 0,
            tweet_id TEXT,
            success INTEGER DEFAULT 1,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            retweets INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0,
            bookmarks INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            engagement_updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_json TEXT NOT NULL,
            captured_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS follower_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            followers INTEGER DEFAULT 0,
            following INTEGER DEFAULT 0,
            total_tweets INTEGER DEFAULT 0,
            captured_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_posts_posted_at ON posts(posted_at);
        CREATE INDEX IF NOT EXISTS idx_posts_content ON posts(content);
        CREATE INDEX IF NOT EXISTS idx_follower_snapshots_date ON follower_snapshots(captured_at);
    """)
    conn.commit()
    return conn


def save_post(db_path, content, category, ticker_mentioned=None,
              is_thread=False, tweet_id=None, success=True):
    """Save a posted tweet to the database."""
    conn = get_db(db_path)
    conn.execute(
        """INSERT INTO posts (content, category, ticker_mentioned, is_thread, tweet_id, success)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (content, category, ticker_mentioned, 1 if is_thread else 0,
         tweet_id, 1 if success else 0)
    )
    conn.commit()
    conn.close()


def get_recent_posts(db_path, n=20):
    """Get the last N posts for deduplication context."""
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT content, category, posted_at FROM posts WHERE success=1 ORDER BY id DESC LIMIT ?",
        (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def check_duplicate(db_path, content, similarity_threshold=0.8):
    """Check if content is too similar to recent posts.
    Uses simple word overlap ratio as a fast similarity check."""
    recent = get_recent_posts(db_path, n=50)
    content_words = set(content.lower().split())

    for post in recent:
        post_words = set(post["content"].lower().split())
        if not content_words or not post_words:
            continue
        overlap = len(content_words & post_words)
        ratio = overlap / max(len(content_words), len(post_words))
        if ratio > similarity_threshold:
            return True  # Too similar
    return False


def log_market_snapshot(db_path, snapshot):
    """Log a market data snapshot for historical reference."""
    conn = get_db(db_path)
    conn.execute(
        "INSERT INTO market_snapshots (snapshot_json) VALUES (?)",
        (json.dumps(snapshot),)
    )
    conn.commit()
    conn.close()


def get_post_count_today(db_path):
    """Get how many posts were made today."""
    conn = get_db(db_path)
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM posts WHERE posted_at LIKE ? AND success=1",
        (f"{today}%",)
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def update_post_engagement(db_path, post_id, views=0, likes=0, retweets=0,
                           replies=0, bookmarks=0, impressions=0):
    """Update engagement metrics for a post."""
    conn = get_db(db_path)
    conn.execute("""
        UPDATE posts SET views=?, likes=?, retweets=?, replies=?, bookmarks=?,
        impressions=?, engagement_score=?, engagement_updated_at=datetime('now')
        WHERE id=?
    """, (views, likes, retweets, replies, bookmarks, impressions,
          views + likes * 3 + retweets * 5 + replies * 2 + bookmarks * 2,
          post_id))
    conn.commit()
    conn.close()


def get_all_posts(db_path, limit=100):
    """Get all posts with engagement data."""
    conn = get_db(db_path)
    rows = conn.execute(
        """SELECT * FROM posts WHERE success=1
           ORDER BY posted_at DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_engagement_stats(db_path):
    """Get aggregate engagement statistics."""
    conn = get_db(db_path)
    row = conn.execute("""
        SELECT
            COUNT(*) as total_posts,
            COALESCE(SUM(views), 0) as total_views,
            COALESCE(SUM(likes), 0) as total_likes,
            COALESCE(SUM(retweets), 0) as total_retweets,
            COALESCE(SUM(replies), 0) as total_replies,
            COALESCE(SUM(bookmarks), 0) as total_bookmarks,
            COALESCE(SUM(impressions), 0) as total_impressions,
            COALESCE(AVG(views), 0) as avg_views,
            COALESCE(AVG(likes), 0) as avg_likes,
            COALESCE(AVG(retweets), 0) as avg_retweets,
            COALESCE(AVG(engagement_score), 0) as avg_engagement
        FROM posts WHERE success=1
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_category_performance(db_path):
    """Get engagement breakdown by content category."""
    conn = get_db(db_path)
    rows = conn.execute("""
        SELECT category,
            COUNT(*) as post_count,
            COALESCE(AVG(views), 0) as avg_views,
            COALESCE(AVG(likes), 0) as avg_likes,
            COALESCE(AVG(retweets), 0) as avg_retweets,
            COALESCE(AVG(engagement_score), 0) as avg_engagement,
            COALESCE(SUM(views), 0) as total_views
        FROM posts WHERE success=1
        GROUP BY category
        ORDER BY avg_engagement DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_posts_by_date(db_path):
    """Get post count and engagement by date."""
    conn = get_db(db_path)
    rows = conn.execute("""
        SELECT DATE(posted_at) as date,
            COUNT(*) as posts,
            COALESCE(SUM(views), 0) as views,
            COALESCE(SUM(likes), 0) as likes,
            COALESCE(SUM(retweets), 0) as retweets
        FROM posts WHERE success=1
        GROUP BY DATE(posted_at)
        ORDER BY date DESC
        LIMIT 30
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_posts(db_path, limit=10, sort_by="engagement_score"):
    """Get top performing posts."""
    conn = get_db(db_path)
    rows = conn.execute(f"""
        SELECT * FROM posts WHERE success=1
        ORDER BY {sort_by} DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_follower_snapshot(db_path, followers, following, total_tweets):
    """Save a follower count snapshot."""
    conn = get_db(db_path)
    conn.execute(
        "INSERT INTO follower_snapshots (followers, following, total_tweets) VALUES (?, ?, ?)",
        (followers, following, total_tweets)
    )
    conn.commit()
    conn.close()


def get_follower_history(db_path, limit=30):
    """Get follower count history."""
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT * FROM follower_snapshots ORDER BY captured_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
