"""Group related subjects and needs, with conservative evidence counts."""

import re
from collections import Counter, defaultdict

from processors.signals import matches, signal_text

TOPICS = {
    "scheduling": (
        "appointment",
        "appointments",
        "scheduling",
        "calendar",
        "booking",
        "rota",
        "shifts",
    ),
    "inventory": ("inventory", "stock", "suppliers", "restocking", "sku"),
    "fulfillment": (
        "shipping",
        "delivery",
        "deliveries",
        "fulfillment",
        "fulfilment",
        "returns",
    ),
    "family_coordination": (
        "family",
        "childcare",
        "school",
        "children",
        "caregiver",
        "caregiving",
        "chores",
    ),
    "meal_planning": ("meal", "meals", "groceries", "cooking", "recipes"),
    "home_maintenance": (
        "maintenance",
        "repairs",
        "cleaning",
        "garden",
        "landlord",
        "tenant",
    ),
    "travel_planning": ("travel", "flight", "flights", "hotel", "holiday", "luggage"),
    "deploy": (
        "deploy",
        "deployment",
        "deployments",
        "deploying",
        "ci/cd",
        "continuous delivery",
        "continuous deployment",
        "release pipeline",
        "rollback",
    ),
    "auth": (
        "auth",
        "authentication",
        "authorization",
        "login",
        "oauth",
        "sso",
        "single sign-on",
        "access control",
    ),
    "payment": (
        "payment",
        "payments",
        "stripe",
        "invoice",
        "invoices",
        "invoicing",
        "billing",
    ),
    "database": (
        "database",
        "databases",
        "postgres",
        "postgresql",
        "mysql",
        "sql",
        "schema migration",
    ),
    "api": (
        "api",
        "apis",
        "webhook",
        "webhooks",
        "integration",
        "integrations",
        "rate limit",
    ),
    "hosting": ("hosting", "cloud", "aws", "server", "servers", "docker", "kubernetes"),
    "pricing": ("pricing", "cost", "costs", "expensive", "budget"),
    "email": ("email", "emails", "smtp", "deliverability"),
    "documentation": ("documentation", "docs", "readme"),
    "performance": ("performance", "latency", "slow", "speed", "optimization"),
    "security": ("security", "vulnerability", "vulnerabilities", "breach"),
    "team": ("team", "collaboration", "slack", "onboarding"),
    "frontend": ("frontend", "css", "react", "component"),
    "mobile": ("mobile", "ios", "android"),
    "analytics": ("analytics", "reporting", "dashboard", "dashboards"),
    "learning": ("learning", "tutorial", "tutorials"),
}
NEEDS = {
    "automation": (
        "manually",
        "manual work",
        "repetitive",
        "automate",
        "automation",
        "copy-paste",
        "copy and paste",
        "hours per",
        "hours a",
    ),
    "cost": ("too expensive", "costs too much", "pricing", "cheaper", "affordable"),
    "reliability": (
        "broken",
        "fails",
        "failing",
        "crash",
        "crashes",
        "outage",
        "unreliable",
        "rollback",
    ),
    "integration": (
        "integrate",
        "integration",
        "integrations",
        "webhook",
        "webhooks",
        "connect",
    ),
    "access_control": ("permissions", "single sign-on", "sso", "access control"),
    "missing_capability": (
        "missing feature",
        "doesn't support",
        "does not support",
        "feature request",
        "wish there was",
    ),
}


def classify_need(point):
    # Parent title supplies subject context only; its intent never scores a comment.
    title = point.get("title") or point.get("metadata", {}).get("parent_title", "")
    excerpt = point.get("evidence_excerpt", "")
    body = signal_text(point.get("body", ""))
    weights = {
        topic: sum(
            3 * matches(term, title) + 2 * matches(term, excerpt) + matches(term, body)
            for term in terms
        )
        for topic, terms in TOPICS.items()
    }
    topic = max(weights, key=weights.get) if any(weights.values()) else "other"
    text = "\n".join((excerpt, signal_text(point.get("text", body))))
    need = next(
        (
            name
            for name, terms in NEEDS.items()
            if any(matches(term, text) for term in terms)
        ),
        "tool_search" if point.get("lead_type") == "alternative_search" else "general",
    )
    return topic, need


def author_key(point):
    author = str(point.get("author", "")).strip().lower()
    if author in {"", "[deleted]", "deleted", "anonymous", "none"} or author.endswith(
        "[bot]"
    ):
        return None
    site = (
        point.get("community", "")
        if point["source"] in {"stackexchange", "discourse"}
        else ""
    )
    return (point["source"], site, author)


def cluster_pain_points(pain_points, supporting_evidence=None):
    groups = defaultdict(dict)
    supporting = defaultdict(list)
    for point in supporting_evidence or []:
        supporting[classify_need(point)].append(point)
    for point in pain_points:
        groups[classify_need(point)][point["post_id"]] = point
    clusters = []
    for (topic, need), indexed in groups.items():
        points = sorted(
            indexed.values(), key=lambda p: (-p["priority_score"], p["post_id"])
        )
        threads = {p.get("parent_id") or p["post_id"] for p in points}
        authors = {key for p in points if (key := author_key(p)) is not None}
        texts = {
            re.sub(r"\W+", " ", (p.get("body") or p.get("title", "")).lower()).strip()
            for p in points
        }
        sources = sorted({p["source"] for p in points})
        seen_threads, seen_authors, seen_texts = set(), set(), set()
        for point in points:
            thread = point.get("parent_id") or point["post_id"]
            author = author_key(point)
            content = re.sub(
                r"\W+", " ", (point.get("body") or point.get("title", "")).lower()
            ).strip()
            if (
                author
                and content
                and thread not in seen_threads
                and author not in seen_authors
                and content not in seen_texts
            ):
                seen_threads.add(thread)
                seen_authors.add(author)
                seen_texts.add(content)
        independent = len(seen_threads)
        repeated = independent >= 2 and topic != "other"
        dates = [p["created_utc"] for p in points if p.get("created_utc")]
        age_counts = dict(Counter(p.get("freshness", "unknown") for p in points))
        priority = min(
            100,
            points[0]["priority_score"]
            + (min(independent - 1, 4) * 5 if repeated else 0)
            + (5 if repeated and len(sources) > 1 else 0),
        )
        clusters.append(
            {
                "id": f"cluster_{topic}_{need}",
                "topic": topic,
                "need": need,
                "pain_points": points,
                "count": len(points),
                "thread_count": len(threads),
                "distinct_author_accounts": len(authors),
                "distinct_text_count": len(texts),
                "repeat_evidence_count": independent,
                "repeated_need": repeated,
                "repeat_validation": "related_theme_only; review original evidence to confirm the same need",
                "evidence_span_days": int((max(dates) - min(dates)) / 86400)
                if dates
                else None,
                "age_counts": age_counts,
                "supporting_evidence": supporting[(topic, need)]
                if topic != "other"
                else [],
                "supporting_match_method": "topic_and_need_only; does not count toward recurrence or priority",
                "cross_source": len(sources) > 1,
                "priority_score": priority,
                "grouping_method": "synonym_need_rules_v1",
                "sources": sources,
                "audiences": sorted(
                    {a for p in points for a in p.get("audiences", [])}
                ),
                "avg_score": sum(p.get("score", 0) for p in points) / len(points),
                "subreddits": sorted(
                    {p["community"] for p in points if p.get("community")}
                ),
                "evidence_urls": list(
                    dict.fromkeys(p["url"] for p in points if p.get("url"))
                ),
                "sentiments": dict(
                    Counter(p.get("sentiment", "curious") for p in points)
                ),
            }
        )
    clusters.sort(
        key=lambda c: (-c["priority_score"], -c["repeat_evidence_count"], c["id"])
    )
    for rank, cluster in enumerate(clusters, 1):
        cluster["rank"] = rank
    return clusters
