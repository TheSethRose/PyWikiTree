from __future__ import annotations

from enum import Enum


class PhotoOrder(str, Enum):
    """Valid values for the ``order`` parameter to ``getPhotos``."""

    PAGE_ID = "PageId"
    UPLOADED = "Uploaded"
    IMAGE_NAME = "ImageName"
    DATE = "Date"


class WatchlistOrder(str, Enum):
    """Valid values for the ``order`` parameter to ``getWatchlist``."""

    USER_ID = "user_id"
    USER_NAME = "user_name"
    USER_LAST_NAME_CURRENT = "user_last_name_current"
    USER_BIRTH_DATE = "user_birth_date"
    USER_DEATH_DATE = "user_death_date"
    PAGE_TOUCHED = "page_touched"


class ConnectionRelation(int, Enum):
    """Valid values for the ``relation`` parameter to ``getConnections``."""

    SHORTEST_PATH = 0
    SHORTEST_EXCLUDING_SPOUSES = 1
    COMMON_ANCESTOR = 2
    COMMON_DESCENDANT = 3
    FATHERS_ONLY = 4
    MOTHERS_ONLY = 5
    YDNA = 6
    MTDNA = 7
    AUDNA = 8
    ANCESTORS_OR_ALL = 11
