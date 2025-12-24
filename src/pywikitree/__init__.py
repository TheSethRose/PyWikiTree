"""Python wrapper for the WikiTree API.

Primary entrypoint: :class:`wikitree_api_client.client.WikiTreeClient`.
"""

from .client import WikiTreeClient
from .enums import ConnectionRelation, PhotoOrder, WatchlistOrder
from .exceptions import WikiTreeAPIError, WikiTreeHTTPError, WikiTreeStatusError

__all__ = [
    "WikiTreeClient",
    "WikiTreeAPIError",
    "WikiTreeHTTPError",
    "WikiTreeStatusError",
    "PhotoOrder",
    "WatchlistOrder",
    "ConnectionRelation",
]
