from .reddit import RedditCollector
from .hackernews import HNCollector
from .github import GitHubCollector
from .x import XCollector
from .stackexchange import StackExchangeCollector

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
