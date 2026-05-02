import httpx
import praw
import time
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from config import PUSHSHIFT_URL, SUBREDDITS, POSTS_PER_SUBREDDIT, REDDIT_PRAW_CONFIG


class RedditCollector:
    def __init__(self, use_praw: bool = False):
        self.pushshift_url = PUSHSHIFT_URL
        self.use_praw = use_praw and bool(REDDIT_PRAW_CONFIG.get("client_id"))
        self.praw_client = None

        if self.use_praw:
            try:
                self.praw_client = praw.Reddit(
                    client_id=REDDIT_PRAW_CONFIG["client_id"],
                    client_secret=REDDIT_PRAW_CONFIG["client_secret"],
                    user_agent=REDDIT_PRAW_CONFIG["user_agent"],
                )
                print("PRAW client initialized successfully")
            except Exception as e:
                print(f"Failed to initialize PRAW: {e}")
                self.use_praw = False

    def collect_all(self, subreddits: Optional[List[str]] = None) -> List[Dict]:
        subreddits = subreddits or SUBREDDITS
        all_posts = []

        for sub in subreddits:
            print(f"Collecting r/{sub}...")
            posts = self.collect_subreddit(sub)
            all_posts.extend(posts)
            print(f"  Collected {len(posts)} posts from r/{sub}")
            time.sleep(1)

        return all_posts

    def collect_subreddit(self, subreddit: str) -> List[Dict]:
        posts = self._collect_via_pushshift(subreddit)

        if self.use_praw and posts:
            enriched = self._enrich_with_praw(posts[:50])
            for i, post in enumerate(posts[:50]):
                if i < len(enriched):
                    post.update(enriched[i])

        return posts

    def _collect_via_pushshift(self, subreddit: str) -> List[Dict]:
        params = {
            "subreddit": subreddit,
            "size": POSTS_PER_SUBREDDIT,
            "sort": "desc",
            "sort_type": "created_utc",
        }

        try:
            response = httpx.get(self.pushshift_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json().get("data", [])

            return [
                {
                    "id": post.get("id"),
                    "title": post.get("title"),
                    "selftext": post.get("selftext", ""),
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "created_utc": post.get("created_utc"),
                    "url": post.get("url", ""),
                    "permalink": post.get("permalink", ""),
                    "subreddit": post.get("subreddit", subreddit),
                    "author": post.get("author", "[deleted]"),
                    "is_self": post.get("is_self", True),
                }
                for post in data
            ]
        except Exception as e:
            print(f"Error collecting {subreddit}: {e}")
            return []

    def _enrich_with_praw(self, posts: List[Dict]) -> List[Dict]:
        if not self.praw_client:
            return []

        enriched = []
        for post in posts[:20]:
            try:
                reddit_post = self.praw_client.submission(id=post["id"])
                comments = []
                reddit_post.comments.replace_more(limit=0)
                for comment in reddit_post.comments[:10]:
                    comments.append(
                        {
                            "id": comment.id,
                            "body": comment.body,
                            "score": comment.score,
                            "author": str(comment.author)
                            if comment.author
                            else "[deleted]",
                        }
                    )
                enriched.append({"comments": comments})
            except Exception:
                enriched.append({"comments": []})

        return enriched
