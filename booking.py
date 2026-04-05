#!/usr/bin/python3
"""
booking.py
~~~~~~~~~~
Wedding Planner — books matching hotel and band slots for a wedding.

Both the hotel and the band offer 550 time slots. This program finds
the earliest slot that is free on both, books it, and helps you manage
your reservations over time. Run it and follow the numbered menu.

Available slot data is cached for up to 30 seconds to reduce unnecessary
API calls. The program always tells you whether it is showing live or
cached data, so you know exactly what you are looking at.

Note: the api.ini file ships with delay = 0.5, which is below the
server's 1-second rate limit. reservationapi.py corrects this silently.
"""

import reservationapi
import configparser
import time
import sys
import warnings

from exceptions import (
    BadRequestError, InvalidTokenError, BadSlotError, NotProcessedError,
    SlotUnavailableError, ReservationLimitError,
)
from requests.exceptions import HTTPError


# Load the configuration file containing the URLs and keys
config = configparser.ConfigParser()
config.read("api.ini")

# Create an API object to communicate with the hotel API
hotel = reservationapi.ReservationApi(
    config['hotel']['url'],
    config['hotel']['key'],
    int(config['global']['retries']),
    float(config['global']['delay']),
)

band = reservationapi.ReservationApi(
    config['band']['url'],
    config['band']['key'],
    int(config['global']['retries']),
    float(config['global']['delay']),
)

# Cache: stores the most recently fetched available-slot list for each service,
# along with when it was fetched. Stale entries are refreshed automatically.
_cache = {
    "hotel": None,  # {"slots": [...], "fetched_at": float}
    "band":  None,
}
CACHE_MAX_AGE_SECONDS = 30


def slot_ids(raw_slots: list) -> list:
    """Convert raw API slot objects ([{"id": "14"}, ...]) to sorted integers."""
    return sorted(int(s["id"]) for s in raw_slots)


def get_available(api: reservationapi.ReservationApi,
                  service: str,
                  force_fresh: bool = False) -> list:
    """
    Return the list of available slot IDs for the given service.

    Uses the in-memory cache unless the cached data is older than
    CACHE_MAX_AGE_SECONDS or force_fresh is True. Always tells the
    user which source the data is coming from.

    Args:
        api:         The ReservationApi instance (hotel or band).
        service:     'hotel' or 'band' — used for cache keying and display.
        force_fresh: Skip the cache and always fetch from the server.

    Returns:
        Sorted list of available slot IDs as integers.
    """
    cached = _cache[service]

    if not force_fresh and cached is not None:
        age = int(time.time() - cached["fetched_at"])
        if age < CACHE_MAX_AGE_SECONDS:
            print(f"  [{service.title()} slots: using cached data, {age}s old "
                  f"— select 'View available slots' to refresh]")
            return cached["slots"]

    print(f"  Fetching current {service} availability from the server...")
    slots = slot_ids(api.get_slots_available())
    _cache[service] = {"slots": slots, "fetched_at": time.time()}
    return slots


def clear_cache():
    """Discard cached slot data so the next availability fetch hits the server."""
    _cache["hotel"] = None
    _cache["band"]  = None


def show_menu():
    """Print the main menu."""
    print()
    print("=" * 45)
    print("       Wedding Planner — Booking Menu")
    print("=" * 45)
    print("  1.  View your current reservations")
    print("  2.  View first 20 available slots")
    print("  3.  Book a specific slot")
    print("  4.  Cancel a reservation")
    print("  5.  View first 5 slots free on both services")
    print("  6.  Reserve the earliest matching slot")
    print("  7.  Cancel all unnecessary reservations")
    print("  8.  Exit")
    print("=" * 45)


def view_current_bookings():
    """
    Show all slots currently held on both the hotel and band APIs.

    Also highlights which slots are matched (booked on both) and
    which are unmatched (booked on only one service).
    """
    print("\nChecking your current reservations...")

    try:
        hotel_held = slot_ids(hotel.get_slots_held())
        band_held  = slot_ids(band.get_slots_held())
    except Exception as e:
        print(f"Could not retrieve your reservations: {e}")
        return

    if not hotel_held and not band_held:
        print("You have no reservations on either the hotel or the band.")
        return

    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots) if slots else "none"

    print(f"\n  Hotel ({len(hotel_held)}/2 slots used): {fmt(hotel_held)}")
    print(f"  Band  ({len(band_held)}/2 slots used): {fmt(band_held)}")

    matched   = sorted(set(hotel_held) & set(band_held))
    only_hotel = [s for s in hotel_held if s not in band_held]
    only_band  = [s for s in band_held  if s not in hotel_held]

    print()
    if matched:
        print(f"  Confirmed match (hotel + band): {fmt(matched)}")
    else:
        print("  No confirmed match yet — you need the same slot on both services.")

    if only_hotel:
        print(f"  Hotel only (no matching band slot):  {fmt(only_hotel)}")
    if only_band:
        print(f"  Band only  (no matching hotel slot): {fmt(only_band)}")


def view_available_slots():
    """
    Show the first 20 available slots on each service.

    Fetches live data from the server and updates the cache.
    """
    print("\nFetching the latest available slots from both services...")

    try:
        hotel_slots = get_available(hotel, "hotel", force_fresh=True)
        band_slots  = get_available(band,  "band",  force_fresh=True)
    except Exception as e:
        print(f"Could not retrieve available slots: {e}")
        return

    def fmt20(slots):
        return ", ".join(str(s) for s in slots[:20]) if slots else "none available"

    print(f"\n  First 20 available hotel slots: {fmt20(hotel_slots)}")
    print(f"  First 20 available band slots:  {fmt20(band_slots)}")
    print(f"\n  (Hotel has {len(hotel_slots)} slots free in total, "
          f"band has {len(band_slots)}.)")


def book_specific_slot():
    """
    Reserve a user-specified slot on both the hotel and the band.

    If the hotel booking succeeds but the band booking fails, the hotel
    reservation is automatically released to keep things tidy.
    """
    print("\nBook a specific slot")
    print("The same slot number will be reserved on both hotel and band.")

    raw = input("\nEnter the slot number to book (or press Enter to go back): ").strip()
    if not raw:
        print("Cancelled.")
        return

    try:
        slot_id = int(raw)
    except ValueError:
        print(f"'{raw}' is not a valid slot number. Please enter a whole number.")
        return

    # Book the hotel first
    print(f"\nReserving slot {slot_id} on the hotel...")
    hotel_booked = False
    try:
        hotel.reserve_slot(slot_id)
        hotel_booked = True
        clear_cache()
        print(f"  Hotel slot {slot_id} reserved successfully.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} is already taken on the hotel. "
              "Try a different slot — use option 5 to find one free on both services.")
    except ReservationLimitError:
        print("  You already hold 2 hotel reservations. "
              "Cancel one with option 4 before booking another.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist (valid range is 1–550).")
    except Exception as e:
        print(f"  Hotel booking failed unexpectedly: {e}")

    if not hotel_booked:
        return

    # Only attempt the band if the hotel succeeded
    print(f"Reserving slot {slot_id} on the band...")
    try:
        band.reserve_slot(slot_id)
        clear_cache()
        print(f"  Band slot {slot_id} reserved successfully.")
        print(f"\nSlot {slot_id} is now confirmed on both hotel and band.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} has just been taken on the band.")
        print(f"  Releasing hotel slot {slot_id} to keep your reservations tidy...")
        _safe_release(hotel, "hotel", slot_id)
    except ReservationLimitError:
        print("  You already hold 2 band reservations, so the band could not be booked.")
        print(f"  Hotel slot {slot_id} was reserved but band was not — "
              "cancel a band reservation and try again.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist on the band side.")
        print(f"  Releasing hotel slot {slot_id}...")
        _safe_release(hotel, "hotel", slot_id)
    except Exception as e:
        print(f"  Band booking failed unexpectedly: {e}")
        print(f"  Releasing hotel slot {slot_id} to avoid leaving a dangling reservation...")
        _safe_release(hotel, "hotel", slot_id)


def cancel_booking():
    """
    Cancel a reservation on the hotel, band, or both.

    Shows your current slots first so you know what is available to cancel.
    """
    print("\nCancel a reservation")

    try:
        hotel_held = slot_ids(hotel.get_slots_held())
        band_held  = slot_ids(band.get_slots_held())
    except Exception as e:
        print(f"Could not retrieve your reservations: {e}")
        return

    if not hotel_held and not band_held:
        print("You have no reservations to cancel.")
        return

    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots) if slots else "none"

    print(f"\n  Hotel slots: {fmt(hotel_held)}")
    print(f"  Band  slots: {fmt(band_held)}")

    raw = input("\nEnter the slot number to cancel (or press Enter to go back): ").strip()
    if not raw:
        print("Cancelled.")
        return

    try:
        slot_id = int(raw)
    except ValueError:
        print(f"'{raw}' is not a valid slot number.")
        return

    on_hotel = slot_id in hotel_held
    on_band  = slot_id in band_held

    if not on_hotel and not on_band:
        print(f"You do not hold slot {slot_id} on either service.")
        return

    # If the slot is on both, ask which to cancel
    if on_hotel and on_band:
        choice = input(
            f"Slot {slot_id} is held on both services. "
            "Cancel on hotel, band, or both? [hotel/band/both]: "
        ).strip().lower()
        on_hotel = choice in ("hotel", "both")
        on_band  = choice in ("band",  "both")
        if not on_hotel and not on_band:
            print("Unrecognised choice. Nothing cancelled.")
            return

    if on_hotel:
        print(f"Cancelling hotel slot {slot_id}...")
        _safe_release(hotel, "hotel", slot_id)

    if on_band:
        print(f"Cancelling band slot {slot_id}...")
        _safe_release(band, "band", slot_id)


def view_matching_slots():
    """
    Show the 5 earliest slots that are free on both hotel and band simultaneously.

    Uses cached availability data where available to save API calls.
    """
    print("\nLooking for slots free on both hotel and band at the same time...")

    try:
        hotel_slots = get_available(hotel, "hotel")
        band_slots  = get_available(band,  "band")
    except Exception as e:
        print(f"Could not fetch availability: {e}")
        return

    matching = sorted(set(hotel_slots) & set(band_slots))

    if not matching:
        print("No slots are currently free on both hotel and band simultaneously.")
        return

    print(f"\n  First 5 slots free on both services:")
    for slot in matching[:5]:
        print(f"    Slot {slot}")
    print(f"\n  ({len(matching)} matching slots available in total.)")


def reserve_earliest_match():
    """
    Find the earliest slot free on both services and book it.

    If you already have a matched pair, this checks whether a better
    (earlier) slot has opened up and upgrades you to it if possible.
    Your existing booking is only released once the new one is confirmed,
    so you are never left without a reservation.

    Strategy:
      1. Read your current holdings to find the best matched pair you have.
      2. Fetch fresh availability from both services.
      3. Find the earliest slot free on both.
      4. If it is better than your current best match, try to book it.
      5. Once both sides confirm, release the old matched pair.
    """
    print("\nSearching for the earliest slot free on both hotel and band...")

    try:
        hotel_held = slot_ids(hotel.get_slots_held())
        band_held  = slot_ids(band.get_slots_held())
    except Exception as e:
        print(f"Could not read your current reservations: {e}")
        return

    matched_now  = sorted(set(hotel_held) & set(band_held))
    current_best = matched_now[0] if matched_now else None

    if current_best:
        print(f"Your current best matching booking is slot {current_best}.")

    # Always fetch fresh data here — stale cache could cause us to miss a slot
    try:
        hotel_avail = get_available(hotel, "hotel", force_fresh=True)
        band_avail  = get_available(band,  "band",  force_fresh=True)
    except Exception as e:
        print(f"Could not fetch available slots: {e}")
        return

    matching_available = sorted(set(hotel_avail) & set(band_avail))

    if not matching_available:
        print("No slots are currently free on both services at the same time.")
        print("Try again in a moment — availability changes constantly.")
        return

    target = matching_available[0]
    print(f"Earliest slot free on both: slot {target}.")

    if current_best is not None and target >= current_best:
        print(f"Your current booking (slot {current_best}) is already the "
              f"earliest available match. Nothing to do.")
        return

    print(f"\nAttempting to book slot {target}...")

    # Make room on hotel if at the 2-reservation limit
    if len(hotel_held) >= 2:
        if not _free_up_slot(hotel, "hotel", hotel_held, band_held):
            return
        hotel_held = slot_ids(hotel.get_slots_held())

    # Reserve hotel side
    print(f"  Reserving hotel slot {target}...")
    try:
        hotel.reserve_slot(target)
        hotel_held.append(target)
        clear_cache()
        print(f"  Hotel slot {target} reserved.")
    except SlotUnavailableError:
        print(f"  Slot {target} was just taken on the hotel. "
              "Run this option again to find the next best slot.")
        return
    except ReservationLimitError:
        print("  Reached the hotel reservation limit unexpectedly. "
              "Use option 7 to clean up unnecessary reservations first.")
        return
    except Exception as e:
        print(f"  Hotel booking failed: {e}")
        return

    # Make room on band if at the 2-reservation limit
    if len(band_held) >= 2:
        if not _free_up_slot(band, "band", band_held, hotel_held):
            _safe_release(hotel, "hotel", target)
            return
        band_held = slot_ids(band.get_slots_held())

    # Reserve band side
    print(f"  Reserving band slot {target}...")
    try:
        band.reserve_slot(target)
        band_held.append(target)
        clear_cache()
        print(f"  Band slot {target} reserved.")
    except SlotUnavailableError:
        print(f"  Slot {target} was just taken on the band.")
        print(f"  Releasing hotel slot {target} to keep things tidy...")
        _safe_release(hotel, "hotel", target)
        print("  Run this option again to find the next best slot.")
        return
    except ReservationLimitError:
        print("  Reached the band reservation limit unexpectedly.")
        print(f"  Releasing hotel slot {target}...")
        _safe_release(hotel, "hotel", target)
        return
    except Exception as e:
        print(f"  Band booking failed: {e}")
        _safe_release(hotel, "hotel", target)
        return

    print(f"\nSlot {target} is now confirmed on both hotel and band.")

    # Release the old matched pair now that the new one is secured
    if current_best is not None and current_best != target:
        print(f"\nReleasing the previous booking at slot {current_best}...")
        _safe_release(hotel, "hotel", current_best)
        _safe_release(band,  "band",  current_best)


def cancel_unneeded():
    """
    Release all reservations except the best matched pair.

    A reservation is 'needed' only if it is part of the earliest slot where
    both hotel and band are confirmed. Everything else gets released.
    """
    print("\nChecking for unnecessary reservations...")

    try:
        hotel_held = slot_ids(hotel.get_slots_held())
        band_held  = slot_ids(band.get_slots_held())
    except Exception as e:
        print(f"Could not retrieve your reservations: {e}")
        return

    if not hotel_held and not band_held:
        print("You have no reservations.")
        return

    matched   = sorted(set(hotel_held) & set(band_held))
    best_match = matched[0] if matched else None

    if best_match is None:
        print("You do not have a confirmed matched pair yet.")
        print("Use option 6 to find and book a matching slot before cleaning up.")
        return

    print(f"Keeping slot {best_match} — confirmed on both hotel and band.")

    to_drop_hotel = [s for s in hotel_held if s != best_match]
    to_drop_band  = [s for s in band_held  if s != best_match]

    if not to_drop_hotel and not to_drop_band:
        print("Nothing to cancel — your reservations are already tidy.")
        return

    for slot in to_drop_hotel:
        print(f"Releasing hotel slot {slot}...")
        _safe_release(hotel, "hotel", slot)

    for slot in to_drop_band:
        print(f"Releasing band slot {slot}...")
        _safe_release(band, "band", slot)

    print(f"\nDone. Slot {best_match} is your confirmed booking on both services.")


def _safe_release(api: reservationapi.ReservationApi, service: str, slot_id: int):
    """
    Attempt to release a slot and report the outcome.

    Prints a clear success or failure message rather than letting an exception
    bubble up silently. Clears the availability cache on success.
    """
    try:
        api.release_slot(slot_id)
        clear_cache()
        print(f"  {service.title()} slot {slot_id} cancelled.")
    except Exception as e:
        print(f"  Could not cancel {service} slot {slot_id}: {e}")


def _free_up_slot(api: reservationapi.ReservationApi,
                  service: str,
                  held: list,
                  other_held: list) -> bool:
    """
    Release one unmatched slot on the given service to stay within the 2-slot limit.

    Prefers to drop the slot with the highest ID that is not matched on the
    other service. Returns True if space was made, False if it was not possible
    (e.g. all held slots are part of matched pairs).

    Args:
        api:        The service API instance to release from.
        service:    'hotel' or 'band', for display purposes.
        held:       Slots currently held on this service.
        other_held: Slots held on the other service (used to identify matches).

    Returns:
        True if a slot was released, False otherwise.
    """
    unmatched = [s for s in held if s not in other_held]
    if not unmatched:
        print(f"  {service.title()} is at the 2-reservation limit and all slots are part "
              "of a matched pair. Cannot make room without losing a confirmed booking.")
        return False

    slot_to_drop = max(unmatched)
    print(f"  {service.title()} is at the reservation limit. "
          f"Releasing unmatched {service} slot {slot_to_drop} to make room...")
    try:
        api.release_slot(slot_to_drop)
        clear_cache()
        print(f"  {service.title()} slot {slot_to_drop} released.")
        return True
    except Exception as e:
        print(f"  Could not release {service} slot {slot_to_drop}: {e}")
        return False


def main():
    """Run the booking menu until the user chooses to exit."""
    print("\nWelcome to the Wedding Planner Booking System.")
    print("Checking your existing reservations on startup...")
    view_current_bookings()

    menu_actions = {
        "1": view_current_bookings,
        "2": view_available_slots,
        "3": book_specific_slot,
        "4": cancel_booking,
        "5": view_matching_slots,
        "6": reserve_earliest_match,
        "7": cancel_unneeded,
    }

    while True:
        show_menu()

        try:
            choice = input("Choose an option (1–8): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            sys.exit(0)

        if choice == "8":
            print("\nGoodbye. Good luck with the wedding!")
            sys.exit(0)

        action = menu_actions.get(choice)
        if action:
            try:
                action()
            except KeyboardInterrupt:
                print("\nAction interrupted. Returning to menu.")
            except Exception as e:
                print(f"\nSomething went wrong: {e}")
                print("Returning to the menu — your data on the server has not changed.")
        else:
            print("Please enter a number between 1 and 8.")


if __name__ == "__main__":
    main()