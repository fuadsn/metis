"""Group specific tasks and obstacles; count independent primary reports only."""

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from hashlib import sha256

from processors.commercial import cluster_commercial_assessment
from processors.problems import problem_key, problem_signature
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


def content_key(point):
    return re.sub(
        r"\W+", " ", signal_text(point.get("body") or point.get("title", "")).lower()
    ).strip()


def copied_text(content, previous):
    if content == previous:
        return True
    # Short common descriptions are not enough to infer copying. Long near-
    # duplicates, including a copied paragraph with an extra sentence, are.
    if min(len(content.split()), len(previous.split())) < 12:
        return False
    a, b = set(content.split()), set(previous.split())
    return SequenceMatcher(None, content, previous, autojunk=False).ratio() >= 0.92 or (
        len(a & b) / min(len(a), len(b)) >= 0.95
        and min(len(content), len(previous)) / max(len(content), len(previous)) >= 0.7
    )


def independent_reports(points):
    selected, excluded = [], []
    # Resolve copies before score ordering: adding emotional wording to a later
    # copy cannot make it the original or manufacture a second platform.
    originals, unique = [], []
    for point in sorted(
        points,
        key=lambda p: (
            p.get("created_utc") or float("inf"),
            len(content_key(p)),
            p["post_id"],
        ),
    ):
        content = content_key(point)
        if content and any(copied_text(content, t) for t in originals):
            excluded.append(
                {"post_id": point["post_id"], "reason": "copied_or_near_duplicate_text"}
            )
        else:
            originals.append(content)
            unique.append(point)
    seen_threads, seen_authors, seen_texts = set(), set(), []
    for point in sorted(unique, key=lambda p: (-p["priority_score"], p["post_id"])):
        thread = point.get("parent_id") or point["post_id"]
        author, content = author_key(point), content_key(point)
        reason = (
            "unknown_author"
            if not author
            else "same_thread"
            if thread in seen_threads
            else "same_author_account"
            if author in seen_authors
            else "empty_evidence"
            if not content
            else "copied_or_near_duplicate_text"
            if any(copied_text(content, t) for t in seen_texts)
            else None
        )
        if reason:
            excluded.append({"post_id": point["post_id"], "reason": reason})
        else:
            selected.append(point)
            seen_threads.add(thread)
            seen_authors.add(author)
            seen_texts.append(content)
    return selected, excluded


def cluster_pain_points(pain_points, supporting_evidence=None):
    groups, supporting = defaultdict(dict), defaultdict(list)
    for point in supporting_evidence or []:
        if problem_signature(point)["matchable"]:
            supporting[problem_key(point)].append(point)
    for point in pain_points:
        if point.get("evidence_role") == "supporting":
            continue
        groups[problem_key(point)][point["post_id"]] = point
    clusters = []
    for key, indexed in groups.items():
        points = sorted(
            indexed.values(), key=lambda p: (-p["priority_score"], p["post_id"])
        )
        independent, excluded = independent_reports(points)
        representative = (independent or points)[0]
        signature = representative.get("problem_signature") or problem_signature(
            representative
        )
        topic, need = classify_need(representative)
        communities = {(p["source"], p.get("community", "")) for p in independent}
        platforms = {p["source"] for p in independent}
        repeated = len(independent) >= 2 and signature["matchable"]
        dates = [p["created_utc"] for p in independent if p.get("created_utc")]
        commercial = cluster_commercial_assessment(independent, repeated)
        clusters.append(
            {
                "id": "cluster_" + sha256(repr(key).encode()).hexdigest()[:16],
                "topic": topic,
                "need": need,
                "problem_signature": signature,
                "pain_points": points,
                "count": len(points),
                "thread_count": len(
                    {p.get("parent_id") or p["post_id"] for p in points}
                ),
                "distinct_author_accounts": len(
                    {author_key(p) for p in points if author_key(p)}
                ),
                "distinct_text_count": len({content_key(p) for p in points}),
                "repeat_evidence_count": len(independent),
                "independent_evidence_ids": [p["post_id"] for p in independent],
                "excluded_from_repeat": excluded,
                "repeated_need": repeated,
                "independent_community_count": len(communities),
                "independent_platform_count": len(platforms),
                "corroboration": "not_established"
                if not repeated
                else "cross_platform_problem"
                if len(platforms) > 1
                else "cross_community_problem"
                if len(communities) > 1
                else "same_community_problem",
                "repeat_validation": "same_task_obstacle_and_audience_rules; independent accounts are not verified identities; review originals",
                "match_explanation": (
                    f"Same task: {signature['task_label']}; same obstacle: {signature['obstacle_label']}; same audience: {signature['audience']}"
                    if signature["matchable"]
                    else "Insufficient or ambiguous task/obstacle evidence; kept separate"
                ),
                "evidence_span_days": int((max(dates) - min(dates)) / 86400)
                if dates
                else None,
                "age_counts": dict(
                    Counter(p.get("freshness", "unknown") for p in points)
                ),
                "supporting_evidence": supporting[key]
                if signature["matchable"]
                else [],
                "supporting_match_method": "same_task_obstacle_and_audience; never counts toward recurrence or commercial evidence",
                "cross_source": repeated and len(platforms) > 1,
                "priority_score": min(
                    100,
                    representative["priority_score"]
                    + (min(len(independent) - 1, 4) * 5 if repeated else 0)
                    + (5 if repeated and len(platforms) > 1 else 0),
                ),
                "commercial": commercial,
                "grouping_method": "task_obstacle_rules_v1",
                "sources": sorted({p["source"] for p in points}),
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
        key=lambda c: (
            -int(c["commercial"]["eligible"]),
            -int(c["cross_source"]),
            -int(c["repeated_need"]),
            -c["priority_score"],
            -c["repeat_evidence_count"],
            c["id"],
        )
    )
    for rank, cluster in enumerate(clusters, 1):
        cluster["rank"] = rank
    return clusters
