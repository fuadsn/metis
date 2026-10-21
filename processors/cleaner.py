import re
from typing import Dict, List

from config import PAIN_KEYWORDS
from models import unique_posts


def clean_posts(posts: List[Dict]) -> List[Dict]:
    cleaned = []
    for post in unique_posts(posts):
        text = "\n".join(part for part in (post["title"], post["body"]) if part).strip()
        if len(text) < 20:
            continue
        cleaned.append(
            {
                **post,
                "text": text,
                "selftext": post["body"],
                "subreddit": post["community"],
            }
        )
    return cleaned


def _matches(phrase, text):
    return (
        re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.IGNORECASE)
        is not None
    )


def extract_pain_points(posts: List[Dict]) -> List[Dict]:
    points = []
    questions = [
        "how do i",
        "how can i",
        "does anyone know",
        "can someone recommend",
        "help me",
    ]
    for post in posts:
        text = post["text"]
        matched = [phrase for phrase in PAIN_KEYWORDS if _matches(phrase, text)]
        labels = [
            str(label).lower() for label in post.get("metadata", {}).get("labels", [])
        ]
        feature_request = any(
            label in {"enhancement", "feature request", "feature-request"}
            for label in labels
        )
        if (
            not matched
            and not feature_request
            and not any(_matches(q, text) for q in questions)
        ):
            continue
        lower = text.lower()
        buying = any(
            _matches(phrase, lower)
            for phrase in ["would pay", "willing to pay", "budget for"]
        )
        alternatives = any(
            _matches(phrase, lower)
            for phrase in ["alternative to", "alternatives to", "looking for"]
        )
        lead_type = (
            "buying_signal"
            if buying
            else "alternative_search"
            if alternatives
            else "workflow_pain"
            if matched or feature_request
            else "support_question"
        )
        # Transparent heuristic priority, not a likelihood of purchase.
        priority = min(
            100,
            20
            + 10 * min(len(matched), 4)
            + 30 * buying
            + 10 * alternatives
            + 10 * feature_request,
        )
        sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        excerpt = next(
            (
                sentence
                for sentence in sentences
                if any(_matches(kw, sentence) for kw in matched)
            ),
            text,
        )
        points.append(
            {
                **post,
                "id": "pp_" + post["id"],
                "post_id": post["id"],
                "matched_keywords": matched,
                "sentiment": _assess_sentiment(lower),
                "is_selftext": bool(post["body"]),
                "lead_type": lead_type,
                "priority_score": priority,
                "evidence_excerpt": excerpt[:600],
                "scoring_method": "keyword_heuristic_v1",
            }
        )
    return sorted(
        points, key=lambda point: (-point["priority_score"], point["post_id"])
    )


def _assess_sentiment(text: str) -> str:
    if any(
        _matches(word, text)
        for word in ["urgent", "desperate", "impossible", "frustrated"]
    ):
        return "desperate"
    if any(_matches(word, text) for word in ["annoying", "tired", "sick", "broken"]):
        return "frustrated"
    return "curious"
