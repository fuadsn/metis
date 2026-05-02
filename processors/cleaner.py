import re
from typing import List, Dict
from config import PAIN_KEYWORDS


def clean_posts(posts: List[Dict]) -> List[Dict]:
    cleaned = []

    for post in posts:
        title = post.get("title", "")
        selftext = post.get("selftext", "")

        if not title or len(title) < 20:
            continue

        text = f"{title} {selftext}".strip()

        cleaned.append(
            {
                "id": post.get("id"),
                "title": title,
                "selftext": selftext[:2000] if selftext else "",
                "text": text,
                "subreddit": post.get("subreddit"),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "created_utc": post.get("created_utc"),
                "url": post.get("url", ""),
                "author": post.get("author", "[deleted]"),
            }
        )

    return cleaned


def extract_pain_points(posts: List[Dict]) -> List[Dict]:
    pain_points = []

    for post in posts:
        text = post.get("text", "").lower()
        title = post.get("title", "")

        matched_keywords = [kw for kw in PAIN_KEYWORDS if kw.lower() in text]

        if matched_keywords or _is_likely_pain(post):
            sentiment = _assess_sentiment(text)

            pain_points.append(
                {
                    "id": f"pp_{post.get('id')}",
                    "post_id": post.get("id"),
                    "title": title,
                    "text": text,
                    "subreddit": post.get("subreddit"),
                    "score": post.get("score", 0),
                    "matched_keywords": matched_keywords,
                    "sentiment": sentiment,
                    "is_selftext": bool(post.get("selftext")),
                }
            )

    return pain_points


def _is_likely_pain(post: Dict) -> bool:
    score = post.get("score", 0)
    text = post.get("text", "")

    if score >= 10:
        return True

    question_indicators = [
        "why is",
        "why does",
        "how do i",
        "how can",
        "can someone",
        "anyone else",
        "is there a",
        "does anyone",
        "help me",
    ]

    for indicator in question_indicators:
        if indicator in text.lower():
            return True

    return False


def _assess_sentiment(text: str) -> str:
    desperate_words = ["urgent", "desperate", "can't", "impossible", "frustrated"]
    annoyed_words = ["annoying", "tired", "sick", "broken", "stupid"]

    if any(w in text for w in desperate_words):
        return "desperate"
    elif any(w in text for w in annoyed_words):
        return "frustrated"
    else:
        return "curious"
