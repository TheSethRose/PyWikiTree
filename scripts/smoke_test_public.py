from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Callable

from pywikitree import PhotoOrder, WikiTreeClient
from pywikitree.exceptions import WikiTreeHTTPError, WikiTreeStatusError


@dataclass(frozen=True, slots=True)
class SmokeResult:
    name: str
    ok: bool
    detail: str
    rate_limited: bool = False


def _is_rate_limited(err: Exception) -> bool:
    msg = str(err).lower()
    return "http 429" in msg or "limit exceeded" in msg or "too many requests" in msg


def _run_with_polite_backoff(
    *,
    name: str,
    fn: Callable[[], str],
    max_429_retries: int,
    cooldown_s: float,
) -> SmokeResult:
    for attempt in range(max_429_retries + 1):
        try:
            detail = fn()
            return SmokeResult(name=name, ok=True, detail=detail, rate_limited=False)
        except (WikiTreeHTTPError, WikiTreeStatusError) as exc:
            rate_limited = _is_rate_limited(exc)
            if rate_limited and attempt < max_429_retries:
                print(f"  ! Rate limited on {name}. Cooling down for {cooldown_s}s...")
                time.sleep(cooldown_s)
                continue
            short = str(exc).replace("\n", " ").strip()
            if len(short) > 140:
                short = short[:140] + "…"
            return SmokeResult(name=name, ok=False, detail=short, rate_limited=rate_limited)
        except Exception as exc:  # noqa: BLE001 - smoke tests should not crash
            short = f"{type(exc).__name__}: {str(exc).replace('\\n', ' ').strip()}"
            if len(short) > 140:
                short = short[:140] + "…"
            return SmokeResult(name=name, ok=False, detail=short, rate_limited=False)

    return SmokeResult(name=name, ok=False, detail="rate-limited", rate_limited=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Public (non-auth) smoke tests for the WikiTree API client. "
            "Prints one line per endpoint and backs off on rate limits."
        )
    )
    parser.add_argument(
        "--app-id",
        default="wikitree_api_client_smoketest",
        help="AppId required by getConnections.",
    )
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=3.0,
        help="Seconds to sleep between endpoint calls.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Client-level retries for transient HTTP failures (429/5xx).",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=2.0,
        help="Client retry backoff base in seconds (exponential).",
    )
    parser.add_argument(
        "--max-retry-sleep",
        type=float,
        default=10.0,
        help="Max sleep duration for client retries.",
    )
    parser.add_argument(
        "--max-429-retries",
        type=int,
        default=2,
        help="Script-level retries when rate-limited (429).",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=30.0,
        help="Sleep duration after a 429 before retrying that endpoint.",
    )
    args = parser.parse_args()

    client = WikiTreeClient(
        app_id=args.app_id,
        max_retries=args.max_retries,
        retry_backoff_s=args.retry_backoff,
        max_retry_sleep_s=args.max_retry_sleep,
    )

    results: list[SmokeResult] = []
    stop_due_to_rate_limit = False

    def pause() -> None:
        if args.sleep_between > 0:
            print(f"  ... pausing {args.sleep_between}s ...")
            time.sleep(args.sleep_between)

    def run_or_skip(name: str, fn: Callable[[], str]) -> None:
        nonlocal stop_due_to_rate_limit
        if stop_due_to_rate_limit:
            print(f"--> Skipping {name} (rate-limited earlier)")
            results.append(
                SmokeResult(
                    name=name,
                    ok=False,
                    detail="SKIP (rate-limited earlier)",
                    rate_limited=True,
                )
            )
            return

        print(f"--> Testing {name}...")
        res = _run_with_polite_backoff(
            name=name,
            max_429_retries=args.max_429_retries,
            cooldown_s=args.cooldown,
            fn=fn,
        )
        results.append(res)
        if res.ok:
            print(f"    ✓ {res.detail}")
        elif res.rate_limited:
            print(f"    ✗ Rate limited")
            stop_due_to_rate_limit = True
        else:
            print(f"    ✗ {res.detail}")
        
        if not stop_due_to_rate_limit:
            pause()

    run_or_skip("getProfile", lambda: _smoke_get_profile(client))

    run_or_skip("getPeople", lambda: _smoke_get_people(client))

    run_or_skip("searchPerson", lambda: _smoke_search_person(client))

    run_or_skip("getCategories", lambda: _smoke_get_categories(client))

    run_or_skip("getPhotos", lambda: _smoke_get_photos(client))

    run_or_skip("getConnections", lambda: _smoke_get_connections(client))

    failed = 0
    for r in results:
        status = "OK" if r.ok else "FAIL"
        print(f"{r.name}:{status} ({r.detail})")
        if not r.ok:
            failed += 1

    return 0 if failed == 0 else 2


def _smoke_get_profile(client: WikiTreeClient) -> str:
    data = client.get_profile("Clemens-1", fields=["Id", "Name", "FirstName", "LastNameAtBirth"])
    profile = data[0].get("profile", {})
    return f"Id={profile.get('Id')} Name={profile.get('Name')}"


def _smoke_get_people(client: WikiTreeClient) -> str:
    data = client.get_people(["Clemens-1", "Windsor-1"], fields=["Id", "Name"], limit=10)
    people = data[0].get("people", {})
    return f"people={len(people) if isinstance(people, dict) else 0}"


def _smoke_search_person(client: WikiTreeClient) -> str:
    data = client.search_person(
        FirstName="Samuel",
        LastName="Clemens",
        limit=3,
        fields="Id,Name,FirstName",
    )
    total = data[0].get("total")
    matches = data[0].get("matches", [])
    return f"total={total} returned={len(matches) if isinstance(matches, list) else 0}"


def _smoke_get_categories(client: WikiTreeClient) -> str:
    data = client.get_categories("Shoshone-1")
    cats = data[0].get("categories", [])
    return f"categories={len(cats) if isinstance(cats, list) else 0}"


def _smoke_get_photos(client: WikiTreeClient) -> str:
    data = client.get_photos("Clemens-1", limit=2, start=0, order=PhotoOrder.DATE)
    photos = data[0].get("photos", [])
    return f"photos={len(photos) if isinstance(photos, list) else 0}"


def _smoke_get_connections(client: WikiTreeClient) -> str:
    data = client.get_connections(["Adams-35", "Windsor-1"], no_path=True)
    if isinstance(data, list) and len(data) > 0:
        path_len = data[0].get("pathLength")
    else:
        path_len = data.get("pathLength") if isinstance(data, dict) else None
    return f"pathLength={path_len}"


if __name__ == "__main__":
    raise SystemExit(main())
