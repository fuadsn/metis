from .github import GitHubCollector
from .hackernews import HNCollector
from .reddit import RedditCollector
from .stackexchange import StackExchangeCollector
from .x import XCollector

COLLECTORS = {
    "hackernews": HNCollector,
    "reddit": RedditCollector,
    "x": XCollector,
    "github": GitHubCollector,
    "stackexchange": StackExchangeCollector,
}
__all__ = [
    "RedditCollector",
    "HNCollector",
    "GitHubCollector",
    "XCollector",
    "StackExchangeCollector",
    "COLLECTORS",
]
