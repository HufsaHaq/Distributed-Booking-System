#!/usr/bin/env python3
"""
cache
~~~~~
In-memory cache for available-slot lists.

Available slot data changes constantly as other clients compete for bookings,
but fetching it on every single operation would be wasteful and risks hitting
the rate limit. This module caches the last-known list for up to 30 seconds,
and always tells the user clearly whether they are seeing live or cached data.
"""

import time
import reservationapi

CACHE_MAX_AGE_SECONDS = 30

# Keyed by service name ('hotel' or 'band'). Each entry is either None or
# a dict with 'slots' (sorted int list) and 'fetched_at' (float timestamp).
_cache: dict = {
    "hotel": None,
    "band":  None,
}


def get_available(api: reservationapi.ReservationApi,
                  service: str,
                  force_fresh: bool = False) -> list:
    """
    Return a sorted list of available slot IDs for the given service.

    Serves from cache if the data is less than CACHE_MAX_AGE_SECONDS old,
    unless force_fresh=True is requested (e.g. before making a booking).
    Always tells the user clearly which source the data is from.
    """
    cached = _cache[service]

    if not force_fresh and cached is not None:
        age = time.time() - cached["fetched_at"]
        if age < CACHE_MAX_AGE_SECONDS:
            remaining = int(CACHE_MAX_AGE_SECONDS - age)
            print(f"  [CACHED] {service.title()} slots - "
                  f"using data fetched {int(age)}s ago, "
                  f"refreshes in {remaining}s "
                  f"(select 'View available slots' to force refresh)")
            return cached["slots"]

    print(f"  [LIVE]   Fetching {service} availability from server...")
    raw   = api.get_slots_available()
    slots = sorted(int(s["id"]) for s in raw)
    _cache[service] = {"slots": slots, "fetched_at": time.time()}
    return slots


def clear_cache():
    """Discard both cached slot lists so the next fetch goes to the server."""
    _cache["hotel"] = None
    _cache["band"]  = None


def cache_ages() -> dict:
    """
    Return the age in seconds of each cached entry, or None if not cached.
    Used by the menu to show a cache status hint.
    """
    now = time.time()
    return {
        service: int(now - entry["fetched_at"]) if entry else None
        for service, entry in _cache.items()
    }