from .discourse import DiscourseCollector
from .github import GitHubCollector
from .hackernews import HNCollector
from .reddit import RedditCollector
from .stackexchange import StackExchangeCollector
from .x import XCollector
from .youtube import YouTubeCollector

COLLECTORS = {
    "hackernews": HNCollector,
    "reddit": RedditCollector,
    "x": XCollector,
    "github": GitHubCollector,
    "stackexchange": StackExchangeCollector,
    "discourse": DiscourseCollector,
    "youtube": YouTubeCollector,
}
__all__ = [
    "RedditCollector",
    "HNCollector",
    "GitHubCollector",
    "XCollector",
    "StackExchangeCollector",
    "COLLECTORS",
    "DiscourseCollector",
    "YouTubeCollector",
]
