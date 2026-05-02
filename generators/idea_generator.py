from typing import List, Dict
import json


def generate_ideas(clusters: List[Dict]) -> List[Dict]:
    ideas = []

    cluster_ideas_map = {
        "api": [
            ("API monitoring with instant SMS alerts", 3, 4),
            ("No-code API builder for non-technical users", 5, 7),
            ("API documentation generator from code", 3, 5),
        ],
        "database": [
            ("Managed PostgreSQL with automatic backups", 2, 5),
            ("Database schema migration tool", 3, 6),
            ("SQL query optimization as a service", 4, 7),
        ],
        "hosting": [
            ("Static site hosting under $5/mo", 2, 3),
            ("One-click Docker deployment", 3, 5),
        ],
        "deploy": [
            ("Zero-config continuous deployment", 3, 5),
            ("Rollback button for any deployment", 3, 6),
        ],
        "payment": [
            ("Stripe alternative for non-profits", 4, 6),
            ("Subscription management dashboard", 3, 5),
        ],
        "auth": [
            ("Passwordless auth for small teams", 3, 4),
            ("SSO for solopreneurs", 4, 6),
        ],
        "pricing": [
            ("Pricing page generator", 2, 3),
            ("Competitor pricing tracker", 4, 7),
        ],
        "email": [
            ("Email warmup automation", 3, 5),
            ("Transactional email under $10/mo", 2, 4),
        ],
        "documentation": [
            ("Notion to docs site generator", 2, 3),
            ("Auto-generated API docs from code", 3, 5),
        ],
        "performance": [
            ("Performance monitoring for small apps", 3, 5),
            ("Image optimization CDN", 2, 4),
        ],
    }

    for cluster in clusters:
        topic = cluster.get("topic", "other")
        count = cluster.get("count", 0)

        topic_ideas = cluster_ideas_map.get(
            topic,
            [
                (f"Tool to help with {topic}", 3, 5),
            ],
        )

        for i, (desc, build_diff, market_diff) in enumerate(topic_ideas):
            demand_signal = count * cluster.get("avg_score", 1)

            novelty = 1 if i == 0 else (3 if i == 1 else 5)

            if novelty == 1:
                novelty_label = "obvious"
            elif novelty <= 3:
                novelty_label = "interesting"
            else:
                novelty_label = "innovative"

            ideas.append(
                {
                    "id": f"idea_{cluster['id']}_{i}",
                    "cluster_id": cluster["id"],
                    "topic": topic,
                    "description": desc,
                    "novelty_score": novelty,
                    "novelty_label": novelty_label,
                    "build_difficulty": build_diff,
                    "market_difficulty": market_diff,
                    "demand_signal": demand_signal,
                    "evidence_count": count,
                    "subreddits": cluster.get("subreddits", [])[:3],
                }
            )

    ideas.sort(key=lambda x: (x["novelty_score"], x["demand_signal"]), reverse=True)

    return ideas


def format_ideas_for_agent(ideas: List[Dict]) -> str:
    output = ["# Product Ideas from Pain Points\n"]

    output.append("## High Priority (High Demand + Innovative)\n")
    for idea in ideas[:5]:
        if idea["novelty_score"] >= 3:
            output.append(f"- **{idea['description']}**")
            output.append(f"  - Topic: {idea['topic']}")
            output.append(
                f"  - Novelty: {idea['novelty_label']} ({idea['novelty_score']}/5)"
            )
            output.append(
                f"  - Build: {idea['build_difficulty']}/10 | Market: {idea['market_difficulty']}/10"
            )
            output.append(f"  - Evidence: {idea['evidence_count']} posts")
            output.append("")

    output.append("## Quick Wins (High Demand + Easy Build)\n")
    for idea in ideas[:5]:
        if idea["build_difficulty"] <= 4 and idea["novelty_score"] <= 2:
            output.append(f"- **{idea['description']}**")
            output.append(
                f"  - Build: {idea['build_difficulty']}/10 | Market: {idea['market_difficulty']}/10"
            )
            output.append("")

    return "\n".join(output)
