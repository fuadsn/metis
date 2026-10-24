from typing import Dict, List

from models import unique_posts
from processors.commercial import commercial_assessment
from processors.problems import problem_signature
from processors.signals import matches, score_post


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


def rank_candidates(posts: List[Dict]) -> List[Dict]:
    points = [
        {
            **post,
            "id": "pp_" + post["id"],
            "post_id": post["id"],
            "sentiment": _assess_sentiment(post["text"]),
            "is_selftext": bool(post["body"]),
            **score_post(post),
        }
        for post in posts
    ]
    for point in points:
        point["problem_signature"] = problem_signature(point)
        point["commercial"] = commercial_assessment(point)
    return sorted(
        points, key=lambda point: (-point["priority_score"], point["post_id"])
    )


def extract_pain_points(posts: List[Dict]) -> List[Dict]:
    return [
        point for point in rank_candidates(posts) if point["lead_quality"] != "noise"
    ]


def _assess_sentiment(text: str) -> str:
    if any(
        matches(word, text)
        for word in ["urgent", "desperate", "impossible", "frustrated"]
    ):
        return "desperate"
    if any(matches(word, text) for word in ["annoying", "tired", "sick", "broken"]):
        return "frustrated"
    return "curious"
