#!/usr/bin/env python3
"""
Reservation-creating menu actions - options 3 and 6.

Option 3 lets the user pick a specific slot.
Option 6 finds and books the earliest slot free on both services,
with retry logic and automatic cleanup of stale reservations.
"""

import time

from exceptions import (
    BadSlotError, SlotUnavailableError, ReservationLimitError,
)

from clients  import hotel, band, MAX_RETRIES, DELAY
from cache    import get_available, clear_cache, clear_service_cache
from helpers  import slot_ids, safe_release, free_up_slot, get_held_with_retry
from parallel import run_both
from colours  import TAG_THREADED
import status


def book_specific_slot():
    """
    Submenu for option 3 - lets the user choose whether to book the hotel
    only, the band only, or both services for the same slot.
    """
    print("\nBook a specific slot")
    print()
    print("  1.  Book hotel only")
    print("  2.  Book band only")
    print("  3.  Book matching (hotel + band, same slot)")
    print("  4.  Back")

    choice = input("\nChoose an option (1–4): ").strip()

    if choice == "1":
        _book_hotel_only()
    elif choice == "2":
        _book_band_only()
    elif choice == "3":
        _book_matching()
    elif choice == "4":
        return
    else:
        print("  Please enter a number between 1 and 4.")


def _prompt_slot_number():
    """
    Ask the user for a slot number in the range 1–550.

    Returns:
        The slot number as an integer, or None if the user cancelled or
        entered an invalid value.
    """
    raw = input("Enter the slot number 1–550 (or press Enter to cancel): ").strip()
    if not raw:
        print("  Cancelled.")
        return None
    try:
        slot = int(raw)
    except ValueError:
        print(f"  '{raw}' is not a valid number. Please enter a whole number between 1 and 550.")
        return None
    if not 1 <= slot <= 550:
        print(f"  Slot {slot} is out of range. Valid slots are 1 to 550.")
        return None
    return slot


def _book_hotel_only():
    """Reserve a single slot on the hotel only."""
    print("\nBook hotel only")

    try:
        hotel_slots = get_available(hotel, "hotel", force_fresh=True)
        if hotel_slots:
            preview = ", ".join(str(s) for s in hotel_slots[:20])
            print(f"\n  Available hotel slots (first 20): {preview}")
        else:
            print("\n  No hotel slots are currently available.")
    except Exception as e:
        print("\n  Could not fetch hotel availability - the server may be temporarily unavailable.")

    slot_id = _prompt_slot_number()
    if slot_id is None:
        return

    print(f"\n  Reserving hotel slot {slot_id}...")
    try:
        hotel.reserve_slot(slot_id)
        clear_service_cache("hotel")
        print(f"  Hotel slot {slot_id} reserved.")
        print("  Note: you still need a matching band slot to confirm the wedding.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} is already taken on the hotel.")
    except ReservationLimitError:
        print("  You already hold 2 hotel reservations. "
              "Cancel one with option 4 before booking another.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist (valid range: 1–550).")
    except Exception as e:
        print("  The hotel reservation did not go through - the server may be temporarily unavailable. Please try again.")


def _book_band_only():
    """Reserve a single slot on the band only."""
    print("\nBook band only")

    try:
        band_slots = get_available(band, "band", force_fresh=True)
        if band_slots:
            preview = ", ".join(str(s) for s in band_slots[:20])
            print(f"\n  Available band slots (first 20): {preview}")
        else:
            print("\n  No band slots are currently available.")
    except Exception as e:
        print("\n  Could not fetch band availability - the server may be temporarily unavailable.")

    slot_id = _prompt_slot_number()
    if slot_id is None:
        return

    print(f"\n  Reserving band slot {slot_id}...")
    try:
        band.reserve_slot(slot_id)
        clear_service_cache("band")
        print(f"  Band slot {slot_id} reserved.")
        print("  Note: you still need a matching hotel slot to confirm the wedding.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} is already taken on the band.")
    except ReservationLimitError:
        print("  You already hold 2 band reservations. "
              "Cancel one with option 4 before booking another.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist (valid range: 1–550).")
    except Exception as e:
        print("  The band reservation did not go through - the server may be temporarily unavailable. Please try again.")


def _book_matching():
    """
    Reserve the same slot on both hotel and band.

    Books hotel first. If the hotel succeeds but the band then fails for any
    reason, the hotel reservation is released automatically so nothing is
    left single.
    """
    print("\nBook matching slot (hotel + band)")

    try:
        hotel_slots = get_available(hotel, "hotel", force_fresh=True)
        band_slots  = get_available(band,  "band",  force_fresh=True)
        matching    = sorted(set(hotel_slots) & set(band_slots))
        if matching:
            preview = ", ".join(str(s) for s in matching[:20])
            print(f"\n  Slots free on both hotel and band (first 20): {preview}")
        else:
            print("\n  No slots are currently free on both services simultaneously.")
    except Exception as e:
        print("\n  Could not fetch availability - the server may be temporarily unavailable.")

    slot_id = _prompt_slot_number()
    if slot_id is None:
        return

    # --- Hotel ---
    print(f"\n  Reserving hotel slot {slot_id}...")
    hotel_booked = False
    try:
        hotel.reserve_slot(slot_id)
        hotel_booked = True
        clear_service_cache("hotel")
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
        print("  The hotel reservation did not go through - the server may be temporarily unavailable.")

    if not hotel_booked:
        return

    # Band (only if hotel succeeded) 
    print(f"  Reserving band slot {slot_id}...")
    try:
        band.reserve_slot(slot_id)
        clear_service_cache("band")
        print(f"  Band slot {slot_id} reserved.")
        print(f"\n  Slot {slot_id} is now confirmed on both hotel and band.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} was just taken on the band.")
        print(f"  Releasing hotel slot {slot_id} to keep reservations tidy...")
        safe_release(hotel, "hotel", slot_id)
    except ReservationLimitError:
        print("  You already hold 2 band reservations. "
              f"Hotel slot {slot_id} was reserved but the band was not - "
              "cancel a band reservation and try again.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist on the band side.")
        print(f"  Releasing hotel slot {slot_id}...")
        safe_release(hotel, "hotel", slot_id)
    except Exception as e:
        print("  The band reservation did not go through - the server may be temporarily unavailable.")
        print(f"  Releasing hotel slot {slot_id} to avoid a dangling reservation...")
        safe_release(hotel, "hotel", slot_id)


def reserve_earliest_match():
    """
    Find the earliest slot free on both services and book it.

      - Read current holdings to find the current best confirmed pair.
      - Retry up to MAX_RETRIES times if no matching slots are visible right now.
      - Once a new pair is confirmed, release the old matched pair and any other stray reservations automatically.
      - The old pair is only released after the new one is secured, so you are never left without at least one confirmed booking.
      - Prints total elapsed time and attempt count on completion
    """
    print("\nSearching for the earliest slot free on both hotel and band...")
    t0 = time.time()
    attempt_used = 0

    try:
        print(f"  {TAG_THREADED} Querying hotel and band held slots simultaneously...")
        hotel_held, band_held = run_both(
            lambda: get_held_with_retry(hotel, "hotel"),
            lambda: get_held_with_retry(band,  "band"),
        )
    except Exception as e:
        print("  Could not read your current reservations - the server may be temporarily unavailable.")
        return

    matched_now  = sorted(set(hotel_held) & set(band_held))
    current_best = matched_now[0] if matched_now else None

    if current_best:
        print(f"  Your current best confirmed booking is slot {current_best}.")

    # Retry loop
    for attempt in range(1, MAX_RETRIES + 1):
        attempt_used = attempt

        try:
            hotel_avail = get_available(hotel, "hotel", force_fresh=True)
            band_avail  = get_available(band,  "band",  force_fresh=True)
        except Exception as e:
            wait = DELAY * (2 ** (attempt - 1))
            print(f"  Could not fetch availability (attempt {attempt}/{MAX_RETRIES}): "
                  f"the server may be temporarily unavailable.")
            if attempt < MAX_RETRIES:
                print(f"  Waiting {wait:.0f}s before retrying...")
                time.sleep(wait)
            continue

        matching = sorted(set(hotel_avail) & set(band_avail))

        if not matching:
            if attempt < MAX_RETRIES:
                wait = DELAY * (2 ** (attempt - 1))
                print(f"  No slots are free on both services right now "
                      f"(attempt {attempt}/{MAX_RETRIES}). "
                      f"Waiting {wait:.0f}s and trying again...")
                time.sleep(wait)
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
            print(f"  {TAG_THREADED} Re-reading held slots from both services simultaneously...")
            hotel_held, band_held = run_both(
                lambda: get_held_with_retry(hotel, "hotel"),
                lambda: get_held_with_retry(band,  "band"),
            )
        except Exception as e:
            print("  Could not re-read reservations - the server may be temporarily unavailable.")
            return

        # Make room on hotel if at the 2-slot cap
        if len(hotel_held) >= 2:
            if not free_up_slot(hotel, "hotel", hotel_held, band_held):
                return
            hotel_held = get_held_with_retry(hotel, "hotel")

        # Reserve hotel side
        print(f"  Reserving hotel slot {target}...")
        hotel_booked = False
        try:
            hotel.reserve_slot(target)
            hotel_booked = True
            clear_service_cache("hotel")
            print(f"  Hotel slot {target} reserved.")
        except SlotUnavailableError:
            wait = DELAY * (2 ** (attempt - 1))
            print(f"  Slot {target} was just taken by another client on the hotel.")
            if attempt < MAX_RETRIES:
                print(f"  Waiting {wait:.0f}s then trying the next best slot "
                      f"(attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
            continue
        except ReservationLimitError:
            print("  You are already holding the maximum of 2 hotel reservations. "
                  "Use option 7 to cancel unnecessary ones first.")
            return
        except Exception as e:
            print(f"  The hotel reservation did not go through. "
                  f"The server said: {e}")
            return

        # Make room on band if at the 2-slot cap
        if len(band_held) >= 2:
            if not free_up_slot(band, "band", band_held, hotel_held):
                safe_release(hotel, "hotel", target)
                return
            band_held = get_held_with_retry(band, "band")

        # Reserve band side
        print(f"  Reserving band slot {target}...")
        try:
            band.reserve_slot(target)
            clear_service_cache("band")
            print(f"  Band slot {target} reserved.")
        except SlotUnavailableError:
            wait = DELAY * (2 ** (attempt - 1))
            print(f"  Slot {target} was just taken by another client on the band.")
            print(f"  Releasing the hotel reservation and waiting {wait:.0f}s "
                  f"before trying again (attempt {attempt}/{MAX_RETRIES})...")
            safe_release(hotel, "hotel", target)
            if attempt < MAX_RETRIES:
                time.sleep(wait)
            continue
        except ReservationLimitError:
            print("  You are already holding the maximum of 2 band reservations.")
            print(f"  Releasing hotel slot {target} - use option 7 to clean up, then try again.")
            safe_release(hotel, "hotel", target)
            return
        except Exception as e:
            print("  The band reservation did not go through - the server may be temporarily unavailable.")
            safe_release(hotel, "hotel", target)
            return

        # Both sides confirmed - success
        print(f"\n  Slot {target} is now confirmed on both hotel and band.")

        # Release the old confirmed pair in parallel now that the new one is secured
        if current_best is not None and current_best != target:
            print(f"  {TAG_THREADED} Releasing old booking (slot {current_best}) on hotel and band simultaneously...")
            run_both(
                lambda s=current_best: safe_release(hotel, "hotel", s),
                lambda s=current_best: safe_release(band,  "band",  s),
            )

        # Auto-clean any remaining stray reservations, then update status
        _auto_cancel_unneeded(target)
        status.update([target], [target])
        elapsed = time.time() - t0
        print(f"\n  Completed in {elapsed:.1f}s across {attempt_used} attempt(s).")
        return

    elapsed = time.time() - t0
    print(f"  Could not secure a matching booking after {MAX_RETRIES} attempts "
          f"({elapsed:.1f}s elapsed).")
    if current_best:
        print(f"  Your existing booking at slot {current_best} is still active.")


def _auto_cancel_unneeded(confirmed_slot: int):
    """
    Drop any stray reservations after a successful booking.

    Called automatically by reserve_earliest_match once the new pair is
    locked in. Option 7 (cancel_unneeded) exists so can also
    trigger this step manually.
    """
    try:
        print(f" {TAG_THREADED} Querying hotel and band held slots simultaneously...")
        hotel_held, band_held = run_both(
            lambda: get_held_with_retry(hotel, "hotel"),
            lambda: get_held_with_retry(band,  "band"),
        )
    except Exception:
        return  # non-critical; the confirmed booking is already secured

    extras_hotel = [s for s in hotel_held if s != confirmed_slot]
    extras_band  = [s for s in band_held  if s != confirmed_slot]

    if not extras_hotel and not extras_band:
        return

    print("\n  Auto-cleaning stray reservations...")
    all_stray = sorted(set(extras_hotel) | set(extras_band))
    for slot in all_stray:
        h = slot in extras_hotel
        b = slot in extras_band
        if h and b:
            print(f"  [THREADED] Releasing stray slot {slot} on hotel and band simultaneously...")
            run_both(
                lambda s=slot: safe_release(hotel, "hotel", s),
                lambda s=slot: safe_release(band,  "band",  s),
            )
        elif h:
            safe_release(hotel, "hotel", slot)
        else:
            safe_release(band, "band", slot)
            