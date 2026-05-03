from typing import List, Dict


def generate_ideas(clusters: List[Dict]) -> List[Dict]:
    ideas = []

    topic_idea_templates = {
        "api": [
            ("API monitoring with instant SMS alerts", 3, 4, 2),
            ("No-code API builder for non-technical users", 5, 7, 3),
            ("API documentation generator from code", 3, 5, 5),
            ("API rate limiting dashboard for indie devs", 2, 4, 2),
        ],
        "database": [
            ("Managed PostgreSQL with automatic backups", 2, 5, 2),
            ("Database schema migration tool", 3, 6, 3),
            ("SQL query optimization as a service", 4, 7, 4),
            ("One-click database cloning for testing", 2, 4, 2),
        ],
        "hosting": [
            ("Static site hosting under $5/mo", 2, 3, 1),
            ("One-click Docker deployment", 3, 5, 2),
            ("Free hosting for open source projects", 2, 6, 2),
        ],
        "deploy": [
            ("Zero-config continuous deployment", 3, 5, 3),
            ("Rollback button for any deployment", 3, 6, 2),
            ("Deploy preview URLs for every PR", 2, 4, 2),
        ],
        "payment": [
            ("Stripe alternative for non-profits", 4, 6, 3),
            ("Subscription management dashboard", 3, 5, 2),
            ("Invoice generator for freelancers", 2, 3, 1),
        ],
        "auth": [
            ("Passwordless auth for small teams", 3, 4, 2),
            ("SSO for solopreneurs", 4, 6, 3),
            ("GitHub OAuth for internal tools", 2, 3, 2),
        ],
        "pricing": [
            ("Pricing page generator", 2, 3, 1),
            ("Competitor pricing tracker", 4, 7, 4),
            ("Cost calculator for AWS/GCP", 2, 4, 2),
        ],
        "email": [
            ("Email warmup automation", 3, 5, 3),
            ("Transactional email under $10/mo", 2, 4, 1),
            ("Email deliverability checker", 3, 5, 3),
        ],
        "documentation": [
            ("Notion to docs site generator", 2, 3, 1),
            ("Auto-generated API docs from code", 3, 5, 4),
            ("Documentation QA tool", 4, 6, 4),
        ],
        "performance": [
            ("Performance monitoring for small apps", 3, 5, 3),
            ("Image optimization CDN", 2, 4, 2),
            ("Core Web Vitals checker", 2, 4, 2),
        ],
        "security": [
            ("Security headers scanner", 2, 4, 2),
            ("Open source dependency audit", 3, 5, 3),
            ("SSL certificate monitor", 2, 3, 1),
        ],
        "devops": [
            ("Infrastructure as code for beginners", 3, 5, 3),
            ("Log aggregation for small teams", 2, 4, 2),
            ("Server health dashboard", 2, 4, 1),
        ],
        "frontend": [
            ("Component library for quick prototypes", 2, 3, 1),
            ("CSS animation generator", 2, 4, 2),
            ("Figma to React converter", 4, 6, 4),
        ],
        "mobile": [
            ("Cross-platform push notifications", 3, 5, 3),
            ("App store optimization tool", 3, 6, 3),
            ("Mobile app analytics for indie devs", 2, 5, 2),
        ],
        "learning": [
            ("Interactive coding tutorials", 2, 4, 2),
            ("AI-powered code review learning", 4, 5, 4),
        ],
        "team": [
            ("Standup bot for Discord/Slack", 2, 4, 1),
            ("Team velocity tracker", 2, 5, 2),
            ("Onboarding checklist for dev teams", 2, 4, 1),
        ],
    }

    for cluster in clusters:
        topic = cluster.get("topic", "other")
        count = cluster.get("count", 0)
        avg_score = cluster.get("avg_score", 1)

        topic_ideas = topic_idea_templates.get(topic, [])

        if not topic_ideas:
            topic_ideas = _generate_fallback_ideas(topic, cluster)

        for i, (desc, build_diff, market_diff, novelty) in enumerate(topic_ideas):
            demand_signal = count * (avg_score / 100)

            ideas.append(
                {
                    "id": f"idea_{cluster['id']}_{i}",
                    "cluster_id": cluster["id"],
                    "topic": topic,
                    "description": desc,
                    "novelty_score": novelty,
                    "novelty_label": _get_novelty_label(novelty),
                    "build_difficulty": build_diff,
                    "market_difficulty": market_diff,
                    "demand_signal": demand_signal,
                    "evidence_count": count,
                }
            )

    ideas.sort(key=lambda x: (x["novelty_score"], x["demand_signal"]), reverse=True)

    return ideas


def _generate_fallback_ideas(topic: str, cluster: Dict) -> List[tuple]:
    topic_clean = topic.lower().strip()

    fallbacks = {
        "other": [],
        "aws": [
            ("AWS cost optimizer for startups", 3, 5, 2),
            ("AWS resource tagging enforcer", 2, 4, 2),
        ],
        "hack": [
            ("AI coding assistant comparison tool", 3, 5, 3),
            ("Hacker news sentiment analyzer", 2, 6, 4),
        ],
        "free": [
            ("Free tier comparison tool", 2, 5, 3),
            ("Freelance rate calculator", 1, 3, 1),
        ],
        "speed": [
            ("Website speed test with recommendations", 2, 4, 2),
            ("CI/CD pipeline optimizer", 3, 5, 3),
        ],
    }

    if topic_clean in fallbacks:
        return fallbacks[topic_clean]

    return [
        (f"SaaS tool for {topic_clean}", 3, 5, 1),
        (f"{topic_clean.title()} management for indie devs", 3, 6, 2),
    ]


def _get_novelty_label(score: int) -> str:
    if score <= 2:
        return "obvious"
    elif score <= 3:
        return "interesting"
    else:
        return "innovative"


def format_ideas_for_agent(ideas: List[Dict]) -> str:
    output = ["# Product Ideas from Pain Points\n"]

    output.append("## High Priority (Innovative + High Demand)\n")
    for idea in ideas:
        if idea["novelty_score"] >= 4:
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

    output.append("## Interesting (Non-obvious)\n")
    count = 0
    for idea in ideas:
        if idea["novelty_score"] == 3 and count < 5:
            output.append(f"- **{idea['description']}**")
            output.append(
                f"  - Build: {idea['build_difficulty']}/10 | Market: {idea['market_difficulty']}/10"
            )
            count += 1
            output.append("")

    output.append("## Quick Wins (Easy Build)\n")
    count = 0
    for idea in ideas:
        if idea["build_difficulty"] <= 3 and count < 5:
            output.append(f"- **{idea['description']}**")
            output.append(
                f"  - Build: {idea['build_difficulty']}/10 | Market: {idea['market_difficulty']}/10"
            )
            count += 1
            output.append("")

    return "\n".join(output)
