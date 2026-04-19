#!/usr/bin/env python3
"""
view_actions

Read-only menu actions - options 1, 2, and 5.

Nothing in here modifies any reservation. These functions just fetch
data and display it clearly. They're safe to run at any time.
"""

from clients import hotel, band
from cache   import get_available
from helpers import slot_ids


def view_current_bookings():
    """
    Show all slots currently held on hotel and band, with match status.

    Highlights confirmed pairs (same slot on both services) and lone
    reservations that still need a match on the other service.
    """
    print("\nChecking your current reservations...")

    try:
        hotel_held = slot_ids(hotel.get_slots_held())
        band_held  = slot_ids(band.get_slots_held())
    except Exception as e:
        print(f"  Could not retrieve your reservations: {e}")
        return

    if not hotel_held and not band_held:
        print("  You have no reservations on either service.")
        return

    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots) if slots else "none"

    print(f"\n  Hotel ({len(hotel_held)}/2 slots held): {fmt(hotel_held)}")
    print(f"  Band  ({len(band_held)}/2 slots held): {fmt(band_held)}")

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


def view_available_slots():
    """
    Fetch live availability from both services and show the first 20 slots each.

    Always hits the server (force_fresh=True) so the user gets current data.
    """
    print("\nFetching the latest available slots from both services...")

    try:
        hotel_slots = get_available(hotel, "hotel", force_fresh=True)
        band_slots  = get_available(band,  "band",  force_fresh=True)
    except Exception as e:
        print(f"  Could not retrieve available slots: {e}")
        return

    def fmt20(slots):
        return ", ".join(str(s) for s in slots[:20]) if slots else "none available"

    print(f"\n  First 20 available hotel slots: {fmt20(hotel_slots)}")
    print(f"  First 20 available band slots:  {fmt20(band_slots)}")
    print(f"\n  (Hotel: {len(hotel_slots)} free in total | "
          f"Band: {len(band_slots)} free in total)")


def view_matching_slots():
    """
    Show the 5 earliest slots currently free on both hotel and band.

    Uses the cache where available to reduce API calls - run option 2
    first if you want fully up-to-date data.
    """
    print("\nLooking for slots free on both hotel and band...")

    try:
        hotel_slots = get_available(hotel, "hotel")
        band_slots  = get_available(band,  "band")
    except Exception as e:
        print(f"  Could not fetch availability: {e}")
        return

    matching = sorted(set(hotel_slots) & set(band_slots))

    if not matching:
        print("  No slots are currently free on both services at the same time.")
        print("  Availability changes constantly - try again in a moment.")
        return

    print(f"\n  First 5 slots free on both services:")
    for slot in matching[:5]:
        print(f"    Slot {slot}")
    print(f"\n  ({len(matching)} matching slots available in total.)")
