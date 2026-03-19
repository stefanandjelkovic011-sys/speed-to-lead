"""
Standalone X Analytics Dashboard — separate from the cleaning company app.
Run: python x_app.py (serves on port 5002)
"""

import os
import sys
from flask import Flask, render_template, request, jsonify

from database import (get_db, get_engagement_stats, get_all_posts,
                      get_category_performance, get_posts_by_date,
                      get_top_posts, get_follower_history)
from config import DB_PATH, X_USERNAME

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), "templates"),
            static_folder=os.path.join(os.path.dirname(__file__), "static"))


@app.route("/")
def dashboard():
    get_db(DB_PATH).close()
    stats = get_engagement_stats(DB_PATH)
    posts = get_all_posts(DB_PATH, limit=50)
    category_perf = get_category_performance(DB_PATH)
    daily_data = get_posts_by_date(DB_PATH)
    top_posts = get_top_posts(DB_PATH, limit=5)
    follower_history = get_follower_history(DB_PATH, limit=30)

    return render_template("x_dashboard.html",
                           stats=stats, posts=posts,
                           category_perf=category_perf,
                           daily_data=daily_data,
                           top_posts=top_posts,
                           follower_history=follower_history,
                           x_username=X_USERNAME)


@app.route("/api/posts")
def api_posts():
    get_db(DB_PATH).close()
    limit = request.args.get("limit", 50, type=int)
    posts = get_all_posts(DB_PATH, limit=limit)
    return jsonify(posts)


@app.route("/api/stats")
def api_stats():
    get_db(DB_PATH).close()
    return jsonify({
        "stats": get_engagement_stats(DB_PATH),
        "category_performance": get_category_performance(DB_PATH),
        "daily_data": get_posts_by_date(DB_PATH),
        "follower_history": get_follower_history(DB_PATH),
    })


if __name__ == "__main__":
    print("\n  X Analytics Dashboard running!")
    print("  Open http://127.0.0.1:5002 in your browser\n")
    app.run(host="127.0.0.1", port=5002, debug=True)
