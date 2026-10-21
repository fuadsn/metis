"""Legacy agent command adapter. This is a JSON CLI, not an MCP transport."""

from cli import latest, main
from pipeline import collect_posts, run_analysis, source_status

__all__ = [
    "collect_posts",
    "run_analysis",
    "source_status",
    "get_ideas",
    "get_clusters",
    "get_leads",
]


def get_ideas(limit=10):
    return latest("ideas", limit)


def get_clusters():
    return latest("clusters", 1000)


def get_leads(limit=20, source=None):
    return latest("leads", limit, source)


if __name__ == "__main__":
    raise SystemExit(main())
