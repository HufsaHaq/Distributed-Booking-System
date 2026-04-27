#!/usr/bin/env python3
"""
Read-only menu actions - options 1, 2, and 5.

Nothing in here modifies any reservation. These functions just fetch
data and display it clearly. They're safe to run at any time.
"""

import time

from clients  import hotel, band
from cache    import get_available
from helpers  import get_held_with_retry
from parallel import run_both
from colours  import TAG_THREADED, CYAN, YELLOW, BOLD, RESET
import status


def view_current_bookings() -> None:
    """
    Show all slots currently held on hotel and band, with match status.

    Fetches both services in parallel to halve the wait time. Uses
    get_held_with_retry so a 404 response (request not yet processed)
    is retried rather than raised as an error. Updates the global status
    line once the holdings are known.

    Returns:
        None. Prints results directly to stdout.
    """
    print("\nChecking your current reservations...")
    t0 = time.time()

    try:
        print(f"  {TAG_THREADED} Querying hotel and band held slots simultaneously...")
        hotel_held, band_held = run_both(
            lambda: get_held_with_retry(hotel, "hotel"),
            lambda: get_held_with_retry(band,  "band"),
        )
    except Exception as e:
        print("  Could not retrieve your reservations - the server may be temporarily unavailable. Please try again.")
        return

    elapsed = time.time() - t0
    status.update(hotel_held, band_held)

    if not hotel_held and not band_held:
        print(f"  You have no reservations on either service.  ({elapsed:.1f}s)")
        return

    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots) if slots else "none"

    print(f"\n  {CYAN}{BOLD}Hotel{RESET} ({len(hotel_held)}/2 slots held): {fmt(hotel_held)}")
    print(f"  {YELLOW}{BOLD}Band {RESET} ({len(band_held)}/2 slots held): {fmt(band_held)}")

    matched    = sorted(set(hotel_held) & set(band_held))
    only_hotel = [s for s in hotel_held if s not in band_held]
    only_band  = [s for s in band_held  if s not in hotel_held]

    print()
    if matched:
        print(f"  Confirmed match (hotel + band): {fmt(matched)}")
    else:
        print("  No confirmed match yet - you need the same slot on both services.")

    if only_hotel:
        print(f"  Hotel only (unmatched): {fmt(only_hotel)}")
    if only_band:
        print(f"  Band only  (unmatched): {fmt(only_band)}")

    print(f"\n  ({elapsed:.1f}s)")


def view_available_slots() -> None:
    """
    Fetch live availability from both services and show the first 20 slots each.

    Always bypasses the cache (force_fresh=True) so the user sees current data.
    Both fetches run in parallel. Updates the cache as a side effect.

    Returns:
        None. Prints results directly to stdout.
    """
    print("\nFetching the latest available slots from both services...")
    t0 = time.time()

    try:
        print(f"  {TAG_THREADED} Fetching availability from hotel and band simultaneously...")
        hotel_slots, band_slots = run_both(
            lambda: get_available(hotel, "hotel", force_fresh=True),
            lambda: get_available(band,  "band",  force_fresh=True),
        )
    except Exception as e:
        print("  Could not fetch slot availability - the server may be temporarily unavailable. Please try again.")
        return

    elapsed = time.time() - t0

    def fmt20(slots):
        return ", ".join(str(s) for s in slots[:20]) if slots else "none available"

    print(f"\n  {CYAN}{BOLD}Hotel{RESET} - first 20 available: {fmt20(hotel_slots)}")
    print(f"  {YELLOW}{BOLD}Band {RESET} - first 20 available: {fmt20(band_slots)}")

    matching = sorted(set(hotel_slots) & set(band_slots))
    if matching:
        fmt20m = ", ".join(str(s) for s in matching[:20])
        print(f"\n  First 20 slots free on {CYAN}hotel{RESET} AND {YELLOW}band{RESET}: {fmt20m}")
    else:
        print("\n  No slots are currently free on both services simultaneously.")

    print(f"\n  Hotel: {len(hotel_slots)} free | "
          f"Band: {len(band_slots)} free | "
          f"Matching: {len(matching)}  ({elapsed:.1f}s)")


def view_matching_slots() -> None:
    """
    Show the 5 earliest slots currently free on both hotel and band.

    Uses the cache where available to reduce API calls. Both fetches run
    in parallel.

    Returns:
        None. Prints results directly to stdout.
    """
    print("\nLooking for slots free on both hotel and band...")
    t0 = time.time()

    try:
        print(f"  {TAG_THREADED} Fetching availability from hotel and band simultaneously...")
        hotel_slots, band_slots = run_both(
            lambda: get_available(hotel, "hotel"),
            lambda: get_available(band,  "band"),
        )
    except Exception as e:
        print("  Could not fetch slot availability - the server may be temporarily unavailable. Please try again.")
        return

    elapsed = time.time() - t0
    matching = sorted(set(hotel_slots) & set(band_slots))

    if not matching:
        print("  No slots are currently free on both services at the same time.")
        print("  Availability changes constantly - try again in a moment.")
        return

    print(f"\n  First 5 slots free on both services:")
    for slot in matching[:5]:
        print(f"    Slot {slot}")
    print(f"\n  ({len(matching)} matching slots available in total  |  {elapsed:.1f}s)")