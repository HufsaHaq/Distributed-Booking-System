#!/usr/bin/env python3
"""
cache
~~~~~
In-memory cache for available-slot lists and held-slot lists.

Available slots change constantly as other clients compete - cached for
30 seconds to reduce API load. Held slots only change when we make a
booking or cancellation - cached for 60 seconds and invalidated
immediately on any operation that changes holdings.

Every fetch and cache hit prints a clear tag so the marker can always
see exactly where data is coming from.
"""

import time
import reservationapi
from colours import TAG_LIVE, TAG_CACHED

CACHE_MAX_AGE_SECONDS  = 30   # available slots TTL
HELD_CACHE_AGE_SECONDS = 60   # held slots TTL - longer, we control when they change

# Available-slot cache: keyed by 'hotel' or 'band'.
# Each entry: {'slots': [int, ...], 'fetched_at': float} or None.
_cache: dict = {
    "hotel": None,
    "band":  None,
}

# Held-slot cache: same structure.
_held_cache: dict = {
    "hotel": None,
    "band":  None,
}


# ── Available slots ────────────────────────────────────────────────────────────

def get_available(api: reservationapi.ReservationApi,
                  service: str,
                  force_fresh: bool = False) -> list:
    """
    Return a sorted list of available slot IDs for the given service.

    Serves from cache if the data is less than CACHE_MAX_AGE_SECONDS old,
    unless force_fresh=True is requested (e.g. before making a booking).
    Always tells the user clearly which source the data is from.

    Args:
        api:         The ReservationApi instance to query if a live fetch is needed.
        service:     Name of the service ('hotel' or 'band'), used for display.
        force_fresh: If True, bypass the cache and always fetch from the server.

    Returns:
        Sorted list of available slot IDs as integers.
    """
    cached = _cache[service]

    if not force_fresh and cached is not None:
        age = time.time() - cached["fetched_at"]
        if age < CACHE_MAX_AGE_SECONDS:
            remaining = int(CACHE_MAX_AGE_SECONDS - age)
            print(f"  {TAG_CACHED} {service.title()} slots - "
                  f"using data fetched {int(age)}s ago, refreshes in {remaining}s "
                  f"(select 'View available slots' to force refresh)")
            return cached["slots"]

    print(f"  {TAG_LIVE} Fetching {service} availability from server...")
    raw   = api.get_slots_available()
    slots = sorted(int(s["id"]) for s in raw)
    _cache[service] = {"slots": slots, "fetched_at": time.time()}
    print(f"  {TAG_LIVE} {service.title()} availability saved to cache "
          f"({len(slots)} slots, refreshes in {CACHE_MAX_AGE_SECONDS}s).")
    return slots


def clear_cache() -> None:
    """Discard both available-slot caches so the next fetch goes to the server."""
    _cache["hotel"] = None
    _cache["band"]  = None


def clear_service_cache(service: str) -> None:
    """
    Discard the available-slot cache for one service only.

    Use this after a booking or cancellation so the other service's
    cache stays valid - only the affected service's availability changed.

    Args:
        service: 'hotel' or 'band'.
    """
    _cache[service] = None


def cache_ages() -> dict:
    """
    Return the age in seconds of each available-slot cache entry, or None.

    Returns:
        Dict mapping service name to age in seconds (int), or None if that
        service has no cached data. Example: {'hotel': 12, 'band': None}.
    """
    now = time.time()
    return {
        service: int(now - entry["fetched_at"]) if entry else None
        for service, entry in _cache.items()
    }


# ── Held slots ─────────────────────────────────────────────────────────────────

def get_held_cached(service: str) -> list | None:
    """
    Return the cached list of held slot IDs for the given service, or None
    if the cache is empty or has expired.

    Prints a clear message in both cases so the user always knows whether
    they are seeing cached or live data.

    Args:
        service: 'hotel' or 'band'.

    Returns:
        Sorted list of held slot IDs as integers, or None if not cached.
    """
    entry = _held_cache[service]
    if entry is None:
        return None
    age = time.time() - entry["fetched_at"]
    if age >= HELD_CACHE_AGE_SECONDS:
        _held_cache[service] = None
        print(f"  {TAG_CACHED} {service.title()} held slots - "
              f"cache expired after {HELD_CACHE_AGE_SECONDS}s, fetching fresh from server...")
        return None
    remaining = int(HELD_CACHE_AGE_SECONDS - age)
    print(f"  {TAG_CACHED} {service.title()} held slots - "
          f"using data from {int(age)}s ago, refreshes in {remaining}s.")
    return entry["slots"]


def update_held_cache(service: str, slots: list) -> None:
    """
    Store the current held slots for a service in the cache.

    Call this whenever a live fetch of held slots succeeds so subsequent
    reads within the TTL can skip the API call.

    Args:
        service: 'hotel' or 'band'.
        slots:   Sorted list of held slot IDs as integers.
    """
    _held_cache[service] = {"slots": slots, "fetched_at": time.time()}


def invalidate_held_cache(service: str) -> None:
    """
    Remove the held-slot cache for a service immediately.

    Call this after any booking or cancellation on that service so the
    next read is forced to go to the server for accurate data.

    Args:
        service: 'hotel' or 'band'.
    """
    _held_cache[service] = None