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
from cache    import (get_available, clear_cache, clear_service_cache,
                      invalidate_held_cache, update_held_cache)
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


def _get_held(service: str, api) -> list:
    """
    Return held slots for a service, using the held cache where available.

    Falls back to a live fetch via get_held_with_retry if the cache is cold.

    Args:
        service: 'hotel' or 'band'.
        api:     The ReservationApi instance for that service.

    Returns:
        Sorted list of held slot IDs as integers.
    """
    from cache import get_held_cached
    cached = get_held_cached(service)
    if cached is not None:
        return cached
    return get_held_with_retry(api, service)


def _ask_drop_slot(service: str, held: list) -> int | None:
    """
    Show the user their current holdings on one service and ask which to drop.

    Args:
        service: 'hotel' or 'band', used for display.
        held:    Slots currently held on that service.

    Returns:
        The slot ID to release, or None if the user cancelled.
    """
    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots)

    print(f"\n  You currently hold 2 {service} reservations: {fmt(held)}")
    print(f"  To book a new {service} slot you must release one of the above first.")
    raw = input(f"  Enter the {service} slot to release (or press Enter to cancel): ").strip()
    if not raw:
        print("  Cancelled.")
        return None
    try:
        to_drop = int(raw)
    except ValueError:
        print(f"  '{raw}' is not a valid slot number.")
        return None
    if to_drop not in held:
        print(f"  You do not hold {service} slot {to_drop}. "
              f"Your {service} slots: {fmt(held)}")
        return None
    return to_drop


def _book_hotel_only() -> None:
    """
    Reserve a single slot on the hotel only.

    If already at the 2-slot hotel limit, shows current holdings and asks
    which one to drop before proceeding.

    Returns:
        None. Prints results directly to stdout.
    """
    from cache import invalidate_held_cache
    print("\nBook hotel only")

    try:
        hotel_slots = get_available(hotel, "hotel", force_fresh=True)
        if hotel_slots:
            preview = ", ".join(str(s) for s in hotel_slots[:20])
            print(f"\n  Available hotel slots (first 20): {preview}")
        else:
            print("\n  No hotel slots are currently available.")
    except Exception:
        print("\n  Could not fetch hotel availability - the server may be temporarily unavailable.")

    # Check holdings before prompting so we handle the limit gracefully
    try:
        hotel_held = _get_held("hotel", hotel)
    except Exception:
        hotel_held = []

    # If at the limit, ask which to drop before we even ask what to book
    slot_to_drop = None
    if len(hotel_held) >= 2:
        slot_to_drop = _ask_drop_slot("hotel", hotel_held)
        if slot_to_drop is None:
            return

    slot_id = _prompt_slot_number()
    if slot_id is None:
        return

    # Release the chosen slot first if needed
    if slot_to_drop is not None:
        print(f"\n  Releasing hotel slot {slot_to_drop} to make room...")
        if not safe_release(hotel, "hotel", slot_to_drop):
            print("  Could not release the slot - cancelling.")
            return

    print(f"\n  Reserving hotel slot {slot_id}...")
    try:
        hotel.reserve_slot(slot_id)
        clear_service_cache("hotel")
        invalidate_held_cache("hotel")
        print(f"  Hotel slot {slot_id} reserved.")
        print("  Note: you still need a matching band slot to confirm the wedding.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} is already taken on the hotel.")
    except ReservationLimitError:
        print("  The hotel is still showing the reservation limit - "
              "the server may not have processed the release yet. Try again shortly.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist (valid range: 1–550).")
    except Exception:
        print("  The hotel reservation did not go through - "
              "the server may be temporarily unavailable. Please try again.")


def _book_band_only() -> None:
    """
    Reserve a single slot on the band only.

    If already at the 2-slot band limit, shows current holdings and asks
    which one to drop before proceeding.

    Returns:
        None. Prints results directly to stdout.
    """
    from cache import invalidate_held_cache
    print("\nBook band only")

    try:
        band_slots = get_available(band, "band", force_fresh=True)
        if band_slots:
            preview = ", ".join(str(s) for s in band_slots[:20])
            print(f"\n  Available band slots (first 20): {preview}")
        else:
            print("\n  No band slots are currently available.")
    except Exception:
        print("\n  Could not fetch band availability - the server may be temporarily unavailable.")

    try:
        band_held = _get_held("band", band)
    except Exception:
        band_held = []

    slot_to_drop = None
    if len(band_held) >= 2:
        slot_to_drop = _ask_drop_slot("band", band_held)
        if slot_to_drop is None:
            return

    slot_id = _prompt_slot_number()
    if slot_id is None:
        return

    if slot_to_drop is not None:
        print(f"\n  Releasing band slot {slot_to_drop} to make room...")
        if not safe_release(band, "band", slot_to_drop):
            print("  Could not release the slot - cancelling.")
            return

    print(f"\n  Reserving band slot {slot_id}...")
    try:
        band.reserve_slot(slot_id)
        clear_service_cache("band")
        invalidate_held_cache("band")
        print(f"  Band slot {slot_id} reserved.")
        print("  Note: you still need a matching hotel slot to confirm the wedding.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} is already taken on the band.")
    except ReservationLimitError:
        print("  The band is still showing the reservation limit - "
              "the server may not have processed the release yet. Try again shortly.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist (valid range: 1–550).")
    except Exception:
        print("  The band reservation did not go through - "
              "the server may be temporarily unavailable. Please try again.")


def _book_matching() -> None:
    """
    Reserve the same slot on both hotel and band.

    Flow:
    1. Fetch available matching slots (with abort/continue choice if fetch fails).
    2. Suggest an earlier slot if one exists before the user enters their choice.
    3. Warn if the chosen slot does not appear free before releasing anything.
    4. Smart limit handling:
       - New slot earlier than current best: auto-releases all, prints each one.
       - New slot not better: asks which specific slot to drop on each service.
    5. Only releases AFTER confirmation so losses are never silent.

    Returns:
        None. Prints results directly to stdout.
    """
    from cache   import invalidate_held_cache
    from colours import RED, RESET as R
    print("\nBook matching slot (hotel + band)")

    # ── Step 1: Fetch available matching slots ────────────────────────────────
    matching     = []
    try:
        print(f"  {TAG_THREADED} Fetching availability from hotel and band simultaneously...")
        hotel_slots, band_slots = run_both(
            lambda: get_available(hotel, "hotel", force_fresh=True),
            lambda: get_available(band,  "band",  force_fresh=True),
        )
        matching = sorted(set(hotel_slots) & set(band_slots))
        if matching:
            preview = ", ".join(str(s) for s in matching[:20])
            print(f"\n  Slots free on both hotel and band (first 20): {preview}")
        else:
            print("\n  No slots are currently free on both services simultaneously.")
    except Exception:
        print(f"\n  {RED}Could not fetch current slot availability - "
              f"the server may be temporarily unavailable.{R}")
        print("\n  What would you like to do?")
        print("    1.  Continue anyway (enter a slot number you already know is free)")
        print("    2.  Return to menu")
        ans = input("\n  Choose (1 or 2): ").strip()
        if ans != "1":
            print("  Returning to menu.")
            return

    # ── Step 2: Get current holdings ─────────────────────────────────────────
    try:
        print(f"  {TAG_THREADED} Checking your current reservations...")
        hotel_held, band_held = run_both(
            lambda: _get_held("hotel", hotel),
            lambda: _get_held("band",  band),
        )
    except Exception:
        hotel_held, band_held = [], []

    matched      = sorted(set(hotel_held) & set(band_held))
    current_best = matched[0] if matched else None

    if current_best:
        print(f"\n  Your current best confirmed booking: Slot {current_best}")

    # ── Step 3: Get slot number from user ─────────────────────────────────────
    slot_id = _prompt_slot_number()
    if slot_id is None:
        return

    # ── Step 4: Re-search - suggest an earlier matching slot if one exists ────
    if matching:
        earlier = [s for s in matching if s < slot_id]
        if earlier:
            best_earlier = earlier[0]   # absolute earliest available
            print(f"\n  Searching for earlier availability...")
            print(f"  Found slot {best_earlier}, which is earlier than slot {slot_id}.")
            ans = input(f"  Book slot {best_earlier} instead? [y/n]: ").strip().lower()
            if ans in ("y", "yes"):
                slot_id = best_earlier
                print(f"  Updated: will book slot {slot_id}.")

    # ── Step 5: Warn if chosen slot not in available list ────────────────────
    # Do this BEFORE releasing anything so the user can back out safely.
    if matching and slot_id not in matching:
        print(f"\n  {RED}Warning:{R} Slot {slot_id} does not appear to be free "
              "on both services right now.")
        print("  If you proceed and the slot is taken, any reservations you "
              "release cannot be recovered.")
        ans = input("  Continue anyway? [y/n]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("  Cancelled - nothing was changed.")
            return

    # ── Step 6: Smart limit handling ──────────────────────────────────────────
    hotel_drop = None
    band_drop  = None

    if len(hotel_held) >= 2 or len(band_held) >= 2:
        # If the new slot is strictly earlier than current best, auto-drop
        if current_best is not None and slot_id < current_best:
            # New slot is a better (earlier) date - auto-drop everything else.
            print(f"\n  Slot {slot_id} is earlier than your current best booking "
                  f"(slot {current_best}) - this is an upgrade.")
            print("  Releasing all current reservations to secure this earlier slot:")
            for s in list(hotel_held):
                if s != slot_id:
                    print(f"    Releasing hotel slot {s} (upgrading from {s} to {slot_id})...")
                    safe_release(hotel, "hotel", s)
            for s in list(band_held):
                if s != slot_id:
                    print(f"    Releasing band slot {s} (upgrading from {s} to {slot_id})...")
                    safe_release(band, "band", s)
            hotel_held = _get_held("hotel", hotel)
            band_held  = _get_held("band",  band)

        else:
            # New slot is not an improvement - ask which ones to drop.
            if len(hotel_held) >= 2:
                hotel_drop = _ask_drop_slot("hotel", hotel_held)
                if hotel_drop is None:
                    return
            if len(band_held) >= 2:
                band_drop = _ask_drop_slot("band", band_held)
                if band_drop is None:
                    return

    # ── Step 7: Release user-chosen slots ─────────────────────────────────────
    if hotel_drop is not None:
        print(f"\n  Releasing hotel slot {hotel_drop} to make room for slot {slot_id}...")
        if not safe_release(hotel, "hotel", hotel_drop):
            print("  Could not release the slot - cancelling to protect your reservations.")
            return

    if band_drop is not None:
        print(f"\n  Releasing band slot {band_drop} to make room for slot {slot_id}...")
        if not safe_release(band, "band", band_drop):
            print("  Could not release the band slot - cancelling.")
            if hotel_drop is not None:
                print(f"  Note: hotel slot {hotel_drop} was already released "
                      "and cannot be recovered automatically.")
            return

    # ── Step 8: Book hotel ────────────────────────────────────────────────────
    print(f"\n  Reserving hotel slot {slot_id}...")
    hotel_booked = False
    try:
        hotel.reserve_slot(slot_id)
        hotel_booked = True
        clear_service_cache("hotel")
        invalidate_held_cache("hotel")
        print(f"  Hotel slot {slot_id} reserved.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} is already taken on the hotel.")
        if hotel_drop or band_drop:
            print(f"  {RED}The slots you released cannot be automatically recovered.{R}")
            print("  Use option 5 to find a new available matching slot.")
    except ReservationLimitError:
        print("  The hotel reservation limit is still showing - "
              "the server may not have processed the release yet. Try again shortly.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist (valid range: 1–550).")
    except Exception:
        print("  The hotel reservation did not go through - "
              "the server may be temporarily unavailable.")

    if not hotel_booked:
        return

    # ── Step 9: Book band ─────────────────────────────────────────────────────
    print(f"  Reserving band slot {slot_id}...")
    try:
        band.reserve_slot(slot_id)
        clear_service_cache("band")
        invalidate_held_cache("band")
        print(f"  Band slot {slot_id} reserved.")
        print(f"\n  Slot {slot_id} is now confirmed on both hotel and band.")
    except SlotUnavailableError:
        print(f"  Slot {slot_id} was just taken on the band.")
        print(f"  Releasing hotel slot {slot_id} to keep reservations tidy...")
        safe_release(hotel, "hotel", slot_id)
    except ReservationLimitError:
        print("  The band is still showing the reservation limit - "
              "the server may not have processed the release yet.")
        print(f"  Hotel slot {slot_id} was reserved but band was not. "
              "Use option 7 to clean up, then try again.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist (valid range: 1–550).")
        print(f"  Releasing hotel slot {slot_id}...")
        safe_release(hotel, "hotel", slot_id)
    except Exception:
        print("  The band reservation did not go through - "
              "the server may be temporarily unavailable.")
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
            invalidate_held_cache("hotel")
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
            invalidate_held_cache("band")
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