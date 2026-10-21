from typing import List, Dict
from collections import defaultdict
import re


def cluster_pain_points(pain_points: List[Dict]) -> List[Dict]:
    if not pain_points:
        return []

    keyword_clusters = defaultdict(list)

    keywords = [
        "api",
        "database",
        "hosting",
        "deploy",
        "aws",
        "server",
        "payment",
        "stripe",
        "auth",
        "authentication",
        "login",
        "frontend",
        "backend",
        "mobile",
        "ios",
        "android",
        "pricing",
        "cost",
        "expensive",
        "cheap",
        "free",
        "email",
        "marketing",
        "seo",
        "analytics",
        "tracking",
        "team",
        "collaboration",
        "communication",
        "Slack",
        "documentation",
        "docs",
        "tutorial",
        "learning",
        "performance",
        "slow",
        "speed",
        "optimization",
        "security",
        "hack",
        "breach",
        "vulnerability",
        "integration",
        "webhook",
        "api",
        "third-party",
        "notification",
        "sms",
        "push",
        "alert",
    ]

    for pp in pain_points:
        text = (pp.get("title", "") + " " + pp.get("text", "")).lower()

        cluster_key = "other"
        for kw in keywords:
            if re.search(r"(?<!\w)" + re.escape(kw.lower()) + r"(?!\w)", text):
                cluster_key = kw.lower()
                break

        keyword_clusters[cluster_key].append(pp)

    clusters = []
    for cluster_key, points in keyword_clusters.items():
        if len(points) >= 1:
            clusters.append(
                {
                    "id": f"cluster_{cluster_key}",
                    "topic": cluster_key,
                    "pain_points": points,
                    "count": len(points),
                    "avg_score": sum(p.get("score", 0) for p in points) / len(points),
                    "subreddits": sorted(
                        {p["subreddit"] for p in points if p.get("subreddit")}
                    ),
                    "sources": sorted(set(p["source"] for p in points)),
                    "evidence_urls": list(
                        dict.fromkeys(p["url"] for p in points if p.get("url"))
                    ),
                    "sentiments": _aggregate_sentiments(points),
                }
            )

    clusters.sort(key=lambda x: x["count"], reverse=True)

    for i, cluster in enumerate(clusters):
        cluster["rank"] = i + 1

    return clusters


def _aggregate_sentiments(points: List[Dict]) -> Dict[str, int]:
    sentiments = defaultdict(int)
    for p in points:
        sentiments[p.get("sentiment", "curious")] += 1
    return dict(sentiments)
