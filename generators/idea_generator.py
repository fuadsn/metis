"""Turn commercially screened, recurring problems into evidence briefs."""

from typing import Dict, List


def generate_ideas(clusters: List[Dict]) -> List[Dict]:
    ideas = []
    for cluster in clusters:
        if not cluster.get("commercial", {}).get("eligible"):
            continue
        signature = cluster["problem_signature"]
        ideas.append(
            {
                "id": f"idea_{cluster['id']}",
                "cluster_id": cluster["id"],
                "topic": cluster["topic"],
                "need": cluster["need"],
                "audiences": cluster["audiences"],
                "description": f"{signature['task_label']}: {signature['obstacle_label'].lower()}",
                "desired_outcome": signature["desired_outcome"],
                "problem_excerpt": signature["obstacle_excerpt"],
                "problem_signature": signature,
                "commercial": cluster["commercial"],
                "demand_signal": cluster["priority_score"],
                "demand_signal_method": "intent_and_independent_problem_reports; not a purchase probability",
                "evidence_count": cluster["count"],
                "independent_evidence_count": cluster["repeat_evidence_count"],
                "independent_evidence_ids": cluster["independent_evidence_ids"],
                "independent_platform_count": cluster["independent_platform_count"],
                "corroboration": cluster["corroboration"],
                "sources": cluster["sources"],
                "evidence_urls": cluster["evidence_urls"],
                "repeated_need": cluster["repeated_need"],
                "novelty_score": None,
                "novelty_label": "unassessed",
                "build_difficulty": None,
                "market_difficulty": None,
                "hypothesis": True,
                "scoring_method": "evidence_brief",
                "validation_questions": [
                    "Does this exact problem still recur for these people?",
                    "Who controls the budget and what does the workaround cost?",
                    "Would they pay to switch from existing solutions?",
                    "Would a service, process change, physical product or software solve it?",
                ],
            }
        )
    # Cluster order already prioritizes commercial eligibility and independent
    # cross-platform corroboration. Do not re-rank by raw popularity or recency.
    return ideas


def format_ideas_for_agent(ideas: List[Dict]) -> str:
    output = ["# Commercial opportunity hypotheses\n"]
    if not ideas:
        output.append(
            "No ideas passed the recurring-problem and economic-evidence filter."
        )
    for idea in ideas:
        output.append(f"- **{idea['description']}**")
        output.append(
            f"  - Independent reports: {idea['independent_evidence_count']}; platforms: {idea['independent_platform_count']}"
        )
        output.append(
            f"  - Commercial basis: {idea['commercial']['basis']}; payment unverified"
        )
        for url in idea["evidence_urls"]:
            output.append(f"  - {url}")
    return "\n".join(output)
