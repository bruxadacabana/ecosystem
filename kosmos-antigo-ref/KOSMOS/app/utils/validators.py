import re
from urllib.parse import urlparse


def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return result.scheme in ("http", "https") and bool(result.netloc)
    except ValueError:
        return False


def detect_feed_type(url: str) -> str:
    """Guess the feed type from a URL. Returns one of: rss, youtube, reddit,
    tumblr, substack, mastodon."""
    lower = url.lower()

    if "youtube.com/channel/" in lower or "youtube.com/@" in lower:
        return "youtube"
    if "reddit.com/r/" in lower:
        return "reddit"
    if re.search(r"[\w-]+\.tumblr\.com", lower):
        return "tumblr"
    if re.search(r"[\w-]+\.substack\.com", lower):
        return "substack"
    if re.search(r"/@[\w_]+", lower):
        return "mastodon"

    return "rss"
