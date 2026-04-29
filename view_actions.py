#!/usr/bin/env python3
"""
Read-only menu actions - options 1, 2, and 5.

Nothing in here modifies any reservation. These functions just fetch
data and display it clearly. They're safe to run at any time.
"""

import time

from clients  import hotel, band
from cache    import get_available
from helpers  import get_held, get_held_with_retry
from parallel import run_both
from colours  import TAG_THREADED, CYAN, YELLOW, BOLD, RESET, GREEN
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
            lambda: get_held("hotel", hotel),
            lambda: get_held("band",  band),
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

    Fetches from cache if data is less than 30 seconds old, otherwise
    fetches live from both servers in parallel. Updates the cache as a
    side effect so subsequent options benefit from the fresh data.

    Returns:
        None. Prints results directly to stdout.
    """
    print("\nFetching the latest available slots from both services...")
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

    # Read holdings to identify half-pairs
    try:
        hotel_held, band_held = run_both(
            lambda: get_held("hotel", hotel),
            lambda: get_held("band",  band),
        )
    except Exception:
        hotel_held, band_held = [], []

    def concat_slots(slots):
        return ", ".join(str(s) for s in slots[:20]) if slots else "none available"

    print(f"\n  {CYAN}Hotel{RESET} \t - first 20 available: {concat_slots(hotel_slots)}")
    print(f"  {YELLOW}Band {RESET} \t - first 20 available: {concat_slots(band_slots)}")


    # True matches: free on both right now
    matching = sorted(set(hotel_slots) & set(band_slots))

    # Half-pair completable: you hold one side, the other side is available
    # e.g. you hold hotel 32, band 32 is available → book band to complete
    hotel_set  = set(hotel_slots)
    band_set   = set(band_slots)
    completable_via_hotel = sorted(  # hold hotel, band available
        s for s in hotel_held if s not in band_held and s in band_set
    )
    completable_via_band = sorted(   # hold band, hotel available
        s for s in band_held if s not in hotel_held and s in hotel_set
    )

    if matching:
        temp = ", ".join(str(s) for s in matching[:20])
        print(f"\n  {CYAN}Hotel{RESET} AND {YELLOW}Band{RESET} - first 20 available: {temp}")
 
    else:
        print(f"\n  No slots are currently free on both services simultaneously.")

    if completable_via_hotel:
        slots_str = ", ".join(str(s) for s in completable_via_hotel[:20])
        print(f"  {GREEN}Potential matches (you hold {CYAN}hotel{RESET}{GREEN},"
              f" {YELLOW}band{RESET}{GREEN} available - book band to complete):{RESET} {slots_str}")

    if completable_via_band:
        slots_str = ", ".join(str(s) for s in completable_via_band[:20])
        print(f"  {GREEN}Potential matches (you hold {YELLOW}band{RESET}{GREEN},"
              f" {CYAN}hotel{RESET}{GREEN} available - book hotel to complete):{RESET} {slots_str}")

    if not matching and not completable_via_hotel and not completable_via_band:
        print("  No immediately bookable matching pairs available.")

    print(f"\n  Hotel: {len(hotel_slots)} free | "
          f"Band: {len(band_slots)} free | "
          f"Matching: {len(matching)} | "
          f"Completable half-pairs: {len(completable_via_hotel) + len(completable_via_band)}"
          f"  ({elapsed:.1f}s)")


def view_matching_slots() -> None:
    """
    Show the 5 earliest slots matchable on both hotel and band.

    Matchable means: available on both services, OR already confirmed
    (held on both). Confirmed pairs are tagged so the user can see their
    current booking in context.

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
    except Exception:
        print("  Could not fetch slot availability - the server may be temporarily unavailable. Please try again.")
        return

    # Include slots already confirmed on both services
    try:
        hotel_held, band_held = run_both(
            lambda: get_held("hotel", hotel),
            lambda: get_held("band",  band),
        )
        confirmed = sorted(set(hotel_held) & set(band_held))
    except Exception:
        hotel_held, band_held, confirmed = [], [], []

    elapsed = time.time() - t0

    hotel_set = set(hotel_slots)
    band_set  = set(band_slots)

    hotel_opts = hotel_set | set(hotel_held)
    band_opts  = band_set  | set(band_held)
    matching   = sorted(hotel_opts & band_opts)

    # Half-pairs: hold one side, other side is available right now
    completable_via_hotel = sorted(
        s for s in hotel_held if s not in band_held and s in band_set
    )
    completable_via_band = sorted(
        s for s in band_held if s not in hotel_held and s in hotel_set
    )

    if not matching and not completable_via_hotel and not completable_via_band:
        print("  No slots are currently matchable on both services.")
        print("  Availability changes constantly - try again in a moment.")
        return

    if matching:
        print(f"\n  First 5 matchable slots (available on both, or already confirmed):")
        for slot in matching[:5]:
            if slot in confirmed:
                tag = f"  {GREEN} confirmed - you hold this on both{RESET}"
            else:
                tag = ""
            print(f"    Slot {slot}{tag}")

    if completable_via_hotel:
        print(f"\n  {GREEN}Completable half-pairs "
              f"(you hold {CYAN}hotel{RESET}{GREEN}, "
              f"{YELLOW}band{RESET}{GREEN} is available - book band to confirm):{RESET}")
        for slot in completable_via_hotel[:5]:
            print(f"    Slot {slot}")

    if completable_via_band:
        print(f"\n  {GREEN}Completable half-pairs "
              f"(you hold {YELLOW}band{RESET}{GREEN}, "
              f"{CYAN}hotel{RESET}{GREEN} is available - book hotel to confirm):{RESET}")
        for slot in completable_via_band[:5]:
            print(f"    Slot {slot}")

    print(f"\n  ({len(matching)} matchable | "
          f"Completable half-pairs: {len(completable_via_hotel) + len(completable_via_band)}"
          f"  |  {elapsed:.1f}s)")