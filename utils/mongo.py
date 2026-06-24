import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)


def normalize_mongodb_url(url: str, db_name: str) -> str:
    """Ensure db name and Atlas-friendly options are in the connection string."""
    parsed = urlparse(url.strip())
    path = parsed.path.strip("/") or db_name
    if not path:
        path = db_name

    query = parse_qs(parsed.query, keep_blank_values=True)
    for key, val in (
        ("retryWrites", "true"),
        ("w", "majority"),
    ):
        if key not in query:
            query[key] = [val]

    new_query = urlencode({k: v[0] for k, v in query.items()})
    return urlunparse(
        (parsed.scheme, parsed.netloc, f"/{path}", parsed.params, new_query, parsed.fragment)
    )
