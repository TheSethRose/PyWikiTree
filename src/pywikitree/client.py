from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests

from .enums import ConnectionRelation, PhotoOrder, WatchlistOrder
from .exceptions import WikiTreeHTTPError, WikiTreeStatusError
from .utils import (
    compact_params,
    ensure_comma_delimited,
    ensure_ignore_ids,
    extract_status_errors,
    join_csv,
)


@dataclass(frozen=True, slots=True)
class AuthInfo:
    """Basic information returned by a successful ``clientLogin``."""

    user_id: int
    user_name: str


class WikiTreeClient:
    """A requests-based client for the WikiTree API.

    The WikiTree API uses a single endpoint and selects operations via an
    ``action`` parameter.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://api.wikitree.com/api.php",
        app_id: str | None = None,
        timeout_s: float = 30.0,
        session: requests.Session | None = None,
        raise_on_api_status: bool = True,
        max_retries: int = 0,
        retry_backoff_s: float = 1.0,
        max_retry_sleep_s: float = 30.0,
        user_agent: str = "pywikitree/0.1.0",
    ) -> None:
        # Load from environment if not explicitly provided
        self._base_url = base_url
        self._app_id = app_id or os.getenv("WIKITREE_APP_ID")
        self._timeout_s = float(os.getenv("WIKITREE_TIMEOUT_S", timeout_s))
        self._session = session or requests.Session()
        self._raise_on_api_status = raise_on_api_status
        
        # Retry configuration with env fallback
        max_retries_env = os.getenv("WIKITREE_MAX_RETRIES")
        self._max_retries = max(0, int(max_retries_env)) if max_retries_env else max(0, int(max_retries))
        
        retry_backoff_env = os.getenv("WIKITREE_RETRY_BACKOFF_S")
        self._retry_backoff_s = float(retry_backoff_env) if retry_backoff_env else float(retry_backoff_s)
        
        self._max_retry_sleep_s = float(max_retry_sleep_s)

        # Be a polite API consumer.
        self._session.headers.setdefault("User-Agent", user_agent)

        self._auth: AuthInfo | None = None

    @property
    def session(self) -> requests.Session:
        return self._session

    @property
    def auth(self) -> AuthInfo | None:
        return self._auth

    def save_cookies(self, path: str | Path) -> None:
        """Persist cookies to a JSON file.

        This is a pragmatic approach for scripts. It stores a simple
        name->value mapping.
        """

        p = Path(path)
        cookie_dict = self._session.cookies.get_dict()
        p.write_text(json.dumps(cookie_dict, indent=2, sort_keys=True), encoding="utf-8")

    def load_cookies(self, path: str | Path, *, domain: str = "api.wikitree.com") -> None:
        """Load cookies from a JSON file created by :meth:`save_cookies`."""

        p = Path(path)
        cookie_dict = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(cookie_dict, dict):
            raise ValueError("Cookie file must be a JSON object mapping cookie names to values")

        for name, value in cookie_dict.items():
            if not isinstance(name, str):
                continue
            self._session.cookies.set(name, str(value), domain=domain, path="/")

    def _post(self, data: Mapping[str, Any], *, allow_redirects: bool = True) -> Any:
        retry_statuses = {429, 502, 503, 504}

        # Ensure appId is included if available
        if self._app_id and "appId" not in data:
            data = {**data, "appId": self._app_id}

        for attempt in range(self._max_retries + 1):
            try:
                resp = self._session.post(
                    self._base_url,
                    data=compact_params(data),
                    timeout=self._timeout_s,
                    allow_redirects=allow_redirects,
                )
            except requests.RequestException as exc:
                if attempt < self._max_retries:
                    sleep_s = min(
                        self._max_retry_sleep_s,
                        max(0.0, self._retry_backoff_s) * (2**attempt),
                    )
                    time.sleep(sleep_s)
                    continue
                raise WikiTreeHTTPError(str(exc)) from exc

            if resp.status_code in retry_statuses and attempt < self._max_retries:
                retry_after = resp.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        sleep_s = float(retry_after)
                    except ValueError:
                        sleep_s = max(0.0, self._retry_backoff_s) * (2**attempt)
                else:
                    sleep_s = max(0.0, self._retry_backoff_s) * (2**attempt)
                time.sleep(min(self._max_retry_sleep_s, sleep_s))
                continue

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                raise WikiTreeHTTPError(f"HTTP {resp.status_code}: {resp.text}") from exc

            try:
                payload = resp.json()
            except ValueError as exc:
                raise WikiTreeHTTPError("Response was not valid JSON") from exc

            if self._raise_on_api_status:
                errors = extract_status_errors(payload)
                if errors:
                    raise WikiTreeStatusError("; ".join(errors))

            return payload

        raise WikiTreeHTTPError("Request failed after retries")

    # --- Authentication ---

    def authenticate(self, *, email: str, password: str, remember_user: bool = True) -> AuthInfo:
        """Authenticate as a WikiTree member (non-browser/offline flow).

        Implements the two-step flow described in `wikitree-api/authentication.md`.
        """

        # Step 1: clientLogin doLogin=1 and capture Location: ...authcode=...
        step1 = {
            "action": "clientLogin",
            "doLogin": 1,
            "wpEmail": email,
            "wpPassword": password,
        }
        if self._app_id:
            step1["appId"] = self._app_id

        raw = self._session.post(
            self._base_url,
            data=compact_params(step1),
            timeout=self._timeout_s,
            allow_redirects=False,
        )
        if raw.status_code != 302:
            raise WikiTreeHTTPError(
                f"Authentication failed: expected 302 redirect, got {raw.status_code}"
            )
        location = raw.headers.get("Location")
        if not location:
            raise WikiTreeHTTPError("Authentication failed: missing Location header")
        match = re.search(r"authcode=(?P<authcode>.+)$", location)
        if match is None:
            raise WikiTreeHTTPError("Authentication failed: authcode not found")
        authcode = match.group("authcode")

        # Step 2: confirm authcode
        step2 = {"action": "clientLogin", "authcode": authcode}
        payload = self._post(step2, allow_redirects=False)
        if not isinstance(payload, dict) or "clientLogin" not in payload:
            raise WikiTreeHTTPError("Authentication failed: unexpected response")

        cl = payload.get("clientLogin")
        if not isinstance(cl, dict):
            raise WikiTreeHTTPError("Authentication failed: missing clientLogin payload")

        result = str(cl.get("result", ""))
        if result.lower() not in {"success", "ok"}:
            raise WikiTreeHTTPError(f"Authentication failed: {result or 'unknown error'}")

        user_id_raw = cl.get("userid")
        user_name_raw = cl.get("username")
        if user_id_raw is None or user_name_raw is None:
            raise WikiTreeHTTPError("Authentication succeeded but userid/username missing")

        info = AuthInfo(user_id=int(user_id_raw), user_name=str(user_name_raw))
        if remember_user:
            self._auth = info
        return info

    def check_login(self, user_id: int) -> Any:
        """Check whether a user is currently signed in (clientLogin checkLogin)."""

        return self._post({"action": "clientLogin", "checkLogin": user_id})

    def logout(self, *, return_url: str | None = None) -> Any:
        """Log out of the API session (clientLogin doLogout=1)."""

        data: dict[str, Any] = {"action": "clientLogin", "doLogout": 1}
        if return_url is not None:
            data["returnURL"] = return_url
        return self._post(data)

    # --- Core request ---

    def request(self, action: str, **params: Any) -> Any:
        """Perform a raw API request with the given action and parameters."""

        return self._post({"action": action, **params})

    # --- Endpoint wrappers (one per documented action) ---

    def get_profile(
        self,
        key: str | int,
        *,
        fields: str | Sequence[str] | None = None,
        bio_format: str | None = None,
        resolve_redirect: bool | None = True,
    ) -> Any:
        return self.request(
            "getProfile",
            key=key,
            fields=join_csv(fields),
            bioFormat=bio_format,
            resolveRedirect=int(resolve_redirect) if resolve_redirect is not None else None,
        )

    def get_person(
        self,
        key: str | int,
        *,
        fields: str | Sequence[str] | None = None,
        bio_format: str | None = None,
        resolve_redirect: bool | None = True,
    ) -> Any:
        return self.request(
            "getPerson",
            key=key,
            fields=join_csv(fields),
            bioFormat=bio_format,
            resolveRedirect=int(resolve_redirect) if resolve_redirect is not None else None,
        )

    def get_people(
        self,
        keys: str | Sequence[str | int],
        *,
        fields: str | Sequence[str] | None = None,
        bio_format: str | None = None,
        siblings: bool | None = None,
        ancestors: int | None = None,
        descendants: int | None = None,
        nuclear: int | None = None,
        min_generation: int | None = None,
        limit: int | None = None,
        start: int | None = None,
    ) -> Any:
        return self.request(
            "getPeople",
            keys=ensure_comma_delimited(keys),
            fields=join_csv(fields),
            bioFormat=bio_format,
            siblings=siblings,
            ancestors=ancestors,
            descendants=descendants,
            nuclear=nuclear,
            minGeneration=min_generation,
            limit=limit,
            start=start,
        )

    def get_ancestors(
        self,
        key: str | int,
        *,
        depth: int,
        fields: str | Sequence[str] | None = None,
        bio_format: str | None = None,
        resolve_redirect: bool | None = True,
    ) -> Any:
        return self.request(
            "getAncestors",
            key=key,
            depth=depth,
            fields=join_csv(fields),
            bioFormat=bio_format,
            resolveRedirect=int(resolve_redirect) if resolve_redirect is not None else None,
        )

    def get_descendants(
        self,
        key: str | int,
        *,
        depth: int,
        fields: str | Sequence[str] | None = None,
        bio_format: str | None = None,
        resolve_redirect: bool | None = True,
    ) -> Any:
        return self.request(
            "getDescendants",
            key=key,
            depth=depth,
            fields=join_csv(fields),
            bioFormat=bio_format,
            resolveRedirect=int(resolve_redirect) if resolve_redirect is not None else None,
        )

    def get_relatives(
        self,
        keys: str | Sequence[str | int],
        *,
        fields: str | Sequence[str] | None = None,
        bio_format: str | None = None,
        get_parents: bool | None = None,
        get_children: bool | None = None,
        get_siblings: bool | None = None,
        get_spouses: bool | None = None,
    ) -> Any:
        return self.request(
            "getRelatives",
            keys=ensure_comma_delimited(keys),
            fields=join_csv(fields),
            bioFormat=bio_format,
            getParents=get_parents,
            getChildren=get_children,
            getSiblings=get_siblings,
            getSpouses=get_spouses,
        )

    def get_watchlist(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        order: WatchlistOrder | str | None = None,
        get_person: bool | None = None,
        get_space: bool | None = None,
        only_living: bool | None = None,
        exclude_living: bool | None = None,
        fields: str | Sequence[str] | None = None,
        bio_format: str | None = None,
    ) -> Any:
        order_value = order.value if isinstance(order, WatchlistOrder) else order
        return self.request(
            "getWatchlist",
            limit=limit,
            offset=offset,
            order=order_value,
            getPerson=get_person,
            getSpace=get_space,
            onlyLiving=only_living,
            excludeLiving=exclude_living,
            fields=join_csv(fields),
            bioFormat=bio_format,
        )

    def get_bio(
        self,
        key: str | int,
        *,
        bio_format: str | None = None,
        resolve_redirect: bool | None = True,
    ) -> Any:
        return self.request(
            "getBio",
            key=key,
            bioFormat=bio_format,
            resolveRedirect=int(resolve_redirect) if resolve_redirect is not None else None,
        )

    def get_photos(
        self,
        key: str | int,
        *,
        resolve_redirect: bool | None = True,
        limit: int | None = None,
        start: int | None = None,
        order: PhotoOrder | str | None = None,
    ) -> Any:
        order_value = order.value if isinstance(order, PhotoOrder) else order
        return self.request(
            "getPhotos",
            key=key,
            resolveRedirect=int(resolve_redirect) if resolve_redirect is not None else None,
            limit=limit,
            start=start,
            order=order_value,
        )

    def get_categories(self, key: str | int) -> Any:
        return self.request("getCategories", key=key)

    def search_person(self, **criteria: Any) -> Any:
        # The API accepts many optional criteria fields. We keep this permissive.
        return self.request("searchPerson", **criteria)

    def get_dna_tests_by_test_taker(self, key: str | int) -> Any:
        return self.request("getDNATestsByTestTaker", key=key)

    def get_connected_profiles_by_dna_test(self, key: str | int, *, dna_id: int) -> Any:
        return self.request("getConnectedProfilesByDNATest", key=key, dna_id=dna_id)

    def get_connected_dna_tests_by_profile(self, key: str | int) -> Any:
        return self.request("getConnectedDNATestsByProfile", key=key)

    def get_connections(
        self,
        keys: str | Sequence[str | int],
        *,
        app_id: str | None = None,
        fields: str | Sequence[str] | None = None,
        relation: ConnectionRelation | int | None = None,
        ignore_ids: None | str | int | Sequence[int] = None,
        no_path: bool | None = None,
    ) -> Any:
        # getConnections can override the global appId if needed
        relation_value = int(relation) if relation is not None else None
        params = {
            "keys": ensure_comma_delimited(keys),
            "fields": join_csv(fields),
            "relation": relation_value,
            "ignoreIds": ensure_ignore_ids(ignore_ids),
            "nopath": int(no_path) if no_path is not None else None,
        }
        if app_id:
            params["appId"] = app_id
        return self.request("getConnections", **params)
