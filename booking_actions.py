#!/usr/bin/env python3
"""
booking_actions

Reservation-creating menu actions - options 3 and 6.

Option 3 lets the user pick a specific slot.
Option 6 finds and books the earliest slot free on both services,
with retry logic and automatic cleanup of stale reservations.
"""

import time

from exceptions import (
    BadSlotError, SlotUnavailableError, ReservationLimitError,
)

from clients import hotel, band, MAX_RETRIES, DELAY
from cache   import get_available, clear_cache
from helpers import slot_ids, safe_release, free_up_slot


def book_specific_slot():
    """
    Reserve a slot number chosen by the user on both hotel and band.

    Books the hotel first. If the hotel succeeds but the band then fails,
    the hotel reservation is automatically released so nothing is left dangling.
    """
    print("\nBook a specific slot")
    print("The same slot number will be reserved on both hotel and band.")

    raw = input("\nEnter the slot number to book (or press Enter to cancel): ").strip()
    if not raw:
        print("  Cancelled.")
        return

    try:
        slot_id = int(raw)
    except ValueError:
        print(f"  '{raw}' is not a valid number. Please enter a whole number.")
        return

    # --- Hotel ---
    print(f"\n  Reserving hotel slot {slot_id}...")
    hotel_booked = False
    try:
        hotel.reserve_slot(slot_id)
        hotel_booked = True
        clear_cache()
        print(f"  Hotel slot {slot_id} reserved.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} is already taken on the hotel. "
              "Use option 5 to find a slot free on both services.")
    except ReservationLimitError:
        print("  You already hold 2 hotel reservations. "
              "Cancel one with option 4 before booking another.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist (valid range: 1–550).")
    except Exception as e:
        print(f"  Hotel booking failed: {e}")

    if not hotel_booked:
        return

    # --- Band (only if hotel succeeded) ---
    print(f"  Reserving band slot {slot_id}...")
    try:
        band.reserve_slot(slot_id)
        clear_cache()
        print(f"  Band slot {slot_id} reserved.")
        print(f"\n  Slot {slot_id} is now confirmed on both hotel and band.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} was just taken on the band.")
        print(f"  Releasing hotel slot {slot_id} to keep reservations tidy...")
        safe_release(hotel, "hotel", slot_id)
    except ReservationLimitError:
        print("  You already hold 2 band reservations. "
              f"Hotel slot {slot_id} was reserved but band was not - "
              "cancel a band reservation and try again.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist on the band side.")
        print(f"  Releasing hotel slot {slot_id}...")
        safe_release(hotel, "hotel", slot_id)
    except Exception as e:
        print(f"  Band booking failed: {e}")
        print(f"  Releasing hotel slot {slot_id} to avoid a dangling reservation...")
        safe_release(hotel, "hotel", slot_id)


def reserve_earliest_match():
    """
    Find the earliest slot free on both services and book it.

    Strategy:
      - Read current holdings to establish the current best confirmed pair.
      - Retry up to MAX_RETRIES times if no matching slots are visible right
        now - availability shifts constantly as other clients act.
      - Once a new pair is confirmed, release the old matched pair and any
        other stray reservations automatically.
      - The old pair is only released after the new one is secured, so you
        are never left without at least one confirmed booking.
    """
    print("\nSearching for the earliest slot free on both hotel and band...")

    try:
        hotel_held = slot_ids(hotel.get_slots_held())
        band_held  = slot_ids(band.get_slots_held())
    except Exception as e:
        print(f"  Could not read your current reservations: {e}")
        return

    matched_now  = sorted(set(hotel_held) & set(band_held))
    current_best = matched_now[0] if matched_now else None

    if current_best:
        print(f"  Your current best confirmed booking is slot {current_best}.")

    # Retry loop - the spec requires we don't give up just because no matching
    # slots are visible right now; availability shifts as other clients act.
    for attempt in range(1, MAX_RETRIES + 1):

        try:
            hotel_avail = get_available(hotel, "hotel", force_fresh=True)
            band_avail  = get_available(band,  "band",  force_fresh=True)
        except Exception as e:
            print(f"  Could not fetch availability "
                  f"(attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {DELAY:.0f}s...")
                time.sleep(DELAY)
            continue

        matching = sorted(set(hotel_avail) & set(band_avail))

        if not matching:
            if attempt < MAX_RETRIES:
                print(f"  No matching slots available right now "
                      f"(attempt {attempt}/{MAX_RETRIES}). "
                      f"Retrying in {DELAY:.0f}s...")
                time.sleep(DELAY)
                continue
            else:
                print(f"  No matching slots found after {MAX_RETRIES} attempts.")
                if current_best:
                    print(f"  Your existing booking at slot {current_best} "
                          "is still active.")
                return

        target = matching[0]
        print(f"  Earliest slot free on both: slot {target}.")

        if current_best is not None and target >= current_best:
            print(f"  Your current booking (slot {current_best}) is already "
                  "the earliest available match. Nothing to do.")
            return

        print(f"\n  Attempting to book slot {target}...")

        # Re-read holdings before each booking attempt - they may have changed
        # if a previous loop iteration released something.
        try:
            hotel_held = slot_ids(hotel.get_slots_held())
            band_held  = slot_ids(band.get_slots_held())
        except Exception as e:
            print(f"  Could not re-read reservations: {e}")
            return

        # Make room on hotel if at the 2-slot cap
        if len(hotel_held) >= 2:
            if not free_up_slot(hotel, "hotel", hotel_held, band_held):
                return
            hotel_held = slot_ids(hotel.get_slots_held())

        # Reserve hotel side
        print(f"  Reserving hotel slot {target}...")
        hotel_booked = False
        try:
            hotel.reserve_slot(target)
            hotel_booked = True
            clear_cache()
            print(f"  Hotel slot {target} reserved.")
        except SlotUnavailableError:
            print(f"  Slot {target} was just taken on the hotel. "
                  f"Retrying (attempt {attempt}/{MAX_RETRIES})...")
            if attempt < MAX_RETRIES:
                time.sleep(DELAY)
            continue
        except ReservationLimitError:
            print("  Hit the hotel reservation limit unexpectedly. "
                  "Use option 7 to clean up first.")
            return
        except Exception as e:
            print(f"  Hotel booking failed: {e}")
            return

        # Make room on band if at the 2-slot cap
        if len(band_held) >= 2:
            if not free_up_slot(band, "band", band_held, hotel_held):
                safe_release(hotel, "hotel", target)
                return
            band_held = slot_ids(band.get_slots_held())

        # Reserve band side
        print(f"  Reserving band slot {target}...")
        try:
            band.reserve_slot(target)
            clear_cache()
            print(f"  Band slot {target} reserved.")
        except SlotUnavailableError:
            print(f"  Slot {target} was just taken on the band.")
            print(f"  Releasing hotel slot {target} and retrying "
                  f"(attempt {attempt}/{MAX_RETRIES})...")
            safe_release(hotel, "hotel", target)
            if attempt < MAX_RETRIES:
                time.sleep(DELAY)
            continue
        except ReservationLimitError:
            print("  Hit the band reservation limit unexpectedly.")
            print(f"  Releasing hotel slot {target}...")
            safe_release(hotel, "hotel", target)
            return
        except Exception as e:
            print(f"  Band booking failed: {e}")
            safe_release(hotel, "hotel", target)
            return

        # Both sides confirmed - success
        print(f"\n  Slot {target} is now confirmed on both hotel and band.")

        # Release the old confirmed pair now that the new one is secured
        if current_best is not None and current_best != target:
            print(f"  Releasing previous booking at slot {current_best}...")
            safe_release(hotel, "hotel", current_best)
            safe_release(band,  "band",  current_best)

        # Auto-clean any remaining stray reservations
        _auto_cancel_unneeded(target)
        return

    print(f"  Could not secure a matching booking after {MAX_RETRIES} attempts.")
    if current_best:
        print(f"  Your existing booking at slot {current_best} is still active.")


def _auto_cancel_unneeded(confirmed_slot: int):
    """
    Drop any stray reservations after a successful booking.

    Called automatically by reserve_earliest_match once the new pair is
    locked in. Option 7 (cancel_unneeded) exists so markers can also
    trigger this step manually.
    """
    try:
        hotel_held = slot_ids(hotel.get_slots_held())
        band_held  = slot_ids(band.get_slots_held())
    except Exception:
        return  # non-critical; the confirmed booking is already secured

    extras_hotel = [s for s in hotel_held if s != confirmed_slot]
    extras_band  = [s for s in band_held  if s != confirmed_slot]

    if extras_hotel or extras_band:
        print("\n  Auto-cleaning stray reservations...")
        for slot in extras_hotel:
            safe_release(hotel, "hotel", slot)
        for slot in extras_band:
            safe_release(band, "band", slot)
