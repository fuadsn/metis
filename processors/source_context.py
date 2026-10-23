"""Explain source selection and keep vendor feedback out of primary demand."""

SOURCE_CONTEXT = {
    "hackernews": {
        "evidence_role": "primary",
        "source_context": "general_discussion",
        "selection_reason": "Firsthand discussion and requests for solutions across providers.",
        "coverage_limit": "Audience is strongly biased toward technology and startups.",
    },
    "stackexchange": {
        "evidence_role": "primary",
        "source_context": "topic_community",
        "selection_reason": "Questions about work and household tasks rather than one vendor's roadmap.",
        "coverage_limit": "Many questions are ordinary advice; a question alone does not establish demand.",
    },
    "github": {
        "evidence_role": "supporting",
        "source_context": "product_issue_tracker",
        "selection_reason": "Implementation and workaround evidence for an independently found problem.",
        "coverage_limit": "Cannot create a primary lead or contribute to repeat evidence.",
    },
    "discourse": {
        "evidence_role": "supporting",
        "source_context": "vendor_community",
        "selection_reason": "The retained adapter reads only Shopify and Monzo product communities.",
        "coverage_limit": "Disabled by default; product feedback cannot establish independent demand.",
    },
}


def source_context(source):
    return SOURCE_CONTEXT.get(
        source,
        {
            "evidence_role": "primary",
            "source_context": "general_discussion",
            "selection_reason": "Explicitly selected community source.",
            "coverage_limit": "Source membership does not verify demand or buyer identity.",
        },
    ).copy()


def community_coverage(candidates, leads, settings):
    """Report yield, including selected communities with no analyzable matches."""
    rows = {}

    def row(source, community):
        key = (source, community)
        if key not in rows:
            rows[key] = {
                "source": source,
                "community": community,
                **source_context(source),
                "analyzed_records": 0,
                "primary_candidates": 0,
                "supporting_records": 0,
                "noise_records": 0,
            }
        return rows[key]

    if "stackexchange" in settings.sources:
        for site, _ in settings.stackexchange_searches():
            row("stackexchange", site)
    lead_ids = {p["post_id"] for p in leads}
    for post in candidates:
        item = row(post["source"], post["community"])
        item["analyzed_records"] += 1
        item["primary_candidates"] += post["post_id"] in lead_ids
        item["supporting_records"] += (
            post["evidence_role"] == "supporting" and post["lead_quality"] != "noise"
        )
        item["noise_records"] += post["lead_quality"] == "noise"
    return [rows[key] for key in sorted(rows)]
