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
from helpers  import slot_ids, safe_release, free_up_slot, get_held_with_retry, get_held
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
        hotel_held = get_held("hotel", hotel)
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
        band_held = get_held("band", band)
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
            lambda: get_held("hotel", hotel),
            lambda: get_held("band",  band),
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

        if current_best is not None and slot_id < current_best:
            # New slot is earlier - we want to upgrade. But we must book the
            # new slot BEFORE releasing the old confirmed pair,
            print(f"\n  Slot {slot_id} is earlier than your current best booking "
                  f"(slot {current_best}) - this is an upgrade.")
            print("  Making room by releasing unmatched slots first "
                  "(confirmed pair kept until new booking is secured)...")

            # Release unmatched hotel slots (not the confirmed pair) to make room
            unmatched_hotel = [s for s in hotel_held if s not in band_held and s != slot_id]
            for s in unmatched_hotel:
                print(f"    Releasing unmatched hotel slot {s}...")
                safe_release(hotel, "hotel", s)

            # Release unmatched band slots
            unmatched_band = [s for s in band_held if s not in hotel_held and s != slot_id]
            for s in unmatched_band:
                print(f"    Releasing unmatched band slot {s}...")
                safe_release(band, "band", s)

            # Refresh so the limit checks below are accurate
            hotel_held = get_held("hotel", hotel)
            band_held  = get_held("band",  band)

            # If the confirmed pair is still filling the cap, we need to
            # temporarily hold both old and new - which means we must drop
            # the confirmed pair now only if we're STILL over the limit.
            # In that case, warn the user clearly.
            if len(hotel_held) >= 2:
                print(f"  Hotel is still at the limit (holding: "
                      f"{', '.join(f'Slot {s}' for s in hotel_held)}).")
                print(f"  Must release the old confirmed hotel slot {current_best} "
                      "to make room - new booking will be attempted immediately after.")
                safe_release(hotel, "hotel", current_best)
                hotel_held = get_held("hotel", hotel)

            if len(band_held) >= 2:
                print(f"  Band is still at the limit (holding: "
                      f"{', '.join(f'Slot {s}' for s in band_held)}).")
                print(f"  Must release the old confirmed band slot {current_best} "
                      "to make room - new booking will be attempted immediately after.")
                safe_release(band, "band", current_best)
                band_held = get_held("band", band)

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
    except SlotUnavailableError:
        print(f"  Slot {slot_id} was just taken on the band.")
        print(f"  Releasing hotel slot {slot_id} to keep reservations tidy...")
        safe_release(hotel, "hotel", slot_id)
        return
    except ReservationLimitError:
        print("  The band reservation limit is still showing - "
              "the server may not have processed the release yet.")
        print(f"  Hotel slot {slot_id} was reserved but band was not. "
              "Use option 7 to clean up, then try again.")
        return
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist (valid range: 1–550).")
        print(f"  Releasing hotel slot {slot_id}...")
        safe_release(hotel, "hotel", slot_id)
        return
    except Exception:
        print("  The band reservation did not go through - "
              "the server may be temporarily unavailable.")
        print(f"  Releasing hotel slot {slot_id} to avoid a dangling reservation...")
        safe_release(hotel, "hotel", slot_id)
        return

    print(f"\n  Slot {slot_id} is now confirmed on both hotel and band.")
    if current_best is not None and slot_id < current_best:
        # Release whatever remains of the old confirmed pair (may already be
        # partially released if we had to make room above)
        remaining_hotel = get_held("hotel", hotel)
        remaining_band  = get_held("band",  band)
        old_hotel = [s for s in remaining_hotel if s != slot_id]
        old_band  = [s for s in remaining_band  if s != slot_id]
        if old_hotel or old_band:
            print("  Releasing remaining old reservations now that new booking is secured:")
            for s in old_hotel:
                print(f"    Releasing hotel slot {s}...")
                safe_release(hotel, "hotel", s)
            for s in old_band:
                print(f"    Releasing band slot {s}...")
                safe_release(band, "band", s)


def reserve_earliest_match():
    """
    Find the earliest slot confirmed on both services and book it.

    Strategy (in order):
    1. Read current holdings. Check for half-pairs (slot on one service
       but not the other) and try to complete them first - that slot may
       already be the earliest possible option.
    2. Build the full set of matchable slots: available slots PLUS any
       slot already held on both services, so confirmed pairs are visible.
    3. If the current confirmed pair is already the earliest matchable
       slot, tell the user and stop - nothing to improve.
    4. Attempt to book the earliest matchable slot. On failure, prompt
       the user whether to keep trying rather than silently retrying.
    5. After a successful booking, release EVERY other reservation on
       both services so exactly one clean pair remains.
    """
    from colours import YELLOW, RESET as R
    print("\nSearching for the earliest slot free on both hotel and band...")
    t0 = time.time()
    attempt_used = 0

    # ── Read current holdings ─────────────────────────────────────────────────
    try:
        print(f"  {TAG_THREADED} Querying hotel and band held slots simultaneously...")
        hotel_held, band_held = run_both(
            lambda: get_held_with_retry(hotel, "hotel"),
            lambda: get_held_with_retry(band,  "band"),
        )
    except Exception:
        print("  Could not read your current reservations - "
              "the server may be temporarily unavailable.")
        return

    matched_now  = sorted(set(hotel_held) & set(band_held))
    current_best = matched_now[0] if matched_now else None

    if current_best:
        print(f"  Your current best confirmed booking: Slot {current_best}.")

    # try to complete any half-pair first
    # A half-pair is a slot held on one service with no partner on the other.
    # Completing it may be better than searching for a brand new slot.
    only_hotel = [s for s in hotel_held if s not in band_held]
    only_band  = [s for s in band_held  if s not in hotel_held]

    for half_slot in sorted(only_hotel):
        print(f"\n  You already hold hotel slot {half_slot} with no matching band slot.")
        print(f"  Attempting to complete this pair by booking band slot {half_slot} first...")
        try:
            band.reserve_slot(half_slot)
            clear_service_cache("band")
            invalidate_held_cache("band")
            print(f"  Band slot {half_slot} reserved - slot {half_slot} is now confirmed!")
            # Release everything else
            _release_all_except(half_slot, hotel_held, band_held + [half_slot])
            status.update([half_slot], [half_slot])
            elapsed = time.time() - t0
            print(f"\n  Completed in {elapsed:.1f}s.")
            return
        except SlotUnavailableError:
            print(f"  Band slot {half_slot} is already taken - will search for a new pair.")
        except ReservationLimitError:
            print(f"  Band reservation limit reached - will try after freeing a slot.")
        except Exception:
            print(f"  Could not book band slot {half_slot} - continuing to full search.")

    for half_slot in sorted(only_band):
        print(f"\n  You already hold band slot {half_slot} with no matching hotel slot.")
        print(f"  Attempting to complete this pair by booking hotel slot {half_slot} first...")
        try:
            hotel.reserve_slot(half_slot)
            clear_service_cache("hotel")
            invalidate_held_cache("hotel")
            print(f"  Hotel slot {half_slot} reserved - slot {half_slot} is now confirmed!")
            _release_all_except(half_slot, hotel_held + [half_slot], band_held)
            status.update([half_slot], [half_slot])
            elapsed = time.time() - t0
            print(f"\n  Completed in {elapsed:.1f}s.")
            return
        except SlotUnavailableError:
            print(f"  Hotel slot {half_slot} is already taken - will search for a new pair.")
        except ReservationLimitError:
            print(f"  Hotel reservation limit reached - will try after freeing a slot.")
        except Exception:
            print(f"  Could not book hotel slot {half_slot} - continuing to full search.")

    # ── Main retry loop ───────────────────────────────────────────────────────
    for attempt in range(1, MAX_RETRIES + 1):
        attempt_used = attempt

        try:
            hotel_avail, band_avail = run_both(
                lambda: get_available(hotel, "hotel", force_fresh=True),
                lambda: get_available(band,  "band",  force_fresh=True),
            )
        except Exception:
            wait = DELAY * (2 ** (attempt - 1))
            print(f"  Could not fetch availability (attempt {attempt}/{MAX_RETRIES}) - "
                  "the server may be temporarily unavailable.")
            if attempt < MAX_RETRIES:
                print(f"  Waiting {wait:.0f}s before retrying...")
                time.sleep(wait)
            continue

        #matching includes slots already held on BOTH services
        hotel_opts = set(hotel_avail) | set(hotel_held)
        band_opts  = set(band_avail)  | set(band_held)
        matching   = sorted(hotel_opts & band_opts)

        if not matching:
            if attempt < MAX_RETRIES:
                wait = DELAY * (2 ** (attempt - 1))
                print(f"  No slots available on both services right now "
                      f"(attempt {attempt}/{MAX_RETRIES}). "
                      f"Waiting {wait:.0f}s and trying again...")
                time.sleep(wait)
                continue
            else:
                print(f"  No matching slots found after {MAX_RETRIES} attempts.")
                if current_best:
                    print(f"  Your existing booking at slot {current_best} is still active.")
                return

        target = matching[0]

        # matching includes slots already held on BOTH services
        if current_best is not None and current_best == target:
            print(f"\n  Your current booking (slot {current_best}) is already the "
                  "earliest possible matching slot available.")
            print("  There is nothing to improve - you have the best possible booking.")
            return

        if current_best is not None and target >= current_best:
            print(f"  Your current booking (slot {current_best}) is already "
                  "the earliest available match. Nothing to do.")
            return

        print(f"\n  Earliest matchable slot: {target}. Attempting to book...")

        # Re-read holdings before booking
        try:
            print(f"  {TAG_THREADED} Re-reading held slots simultaneously...")
            hotel_held, band_held = run_both(
                lambda: get_held_with_retry(hotel, "hotel"),
                lambda: get_held_with_retry(band,  "band"),
            )
        except Exception:
            print("  Could not re-read reservations - "
                  "the server may be temporarily unavailable.")
            return

        # Make room on hotel if needed
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
            print(f"  Slot {target} was just taken by another client on the hotel.")
            #prompt user instead of silently retrying
            if attempt < MAX_RETRIES:
                ans = input(f"  Keep searching for the next earliest slot? [y/n]: ").strip().lower()
                if ans not in ("y", "yes"):
                    print("  Search cancelled. Returning to menu.")
                    return
                wait = DELAY * (2 ** (attempt - 1))
                print(f"  Waiting {wait:.0f}s before next attempt...")
                time.sleep(wait)
            continue
        except ReservationLimitError:
            print("  You are already holding the maximum of 2 hotel reservations. "
                  "Use option 7 to cancel unnecessary ones first.")
            return
        except Exception:
            print("  The hotel reservation did not go through - "
                  "the server may be temporarily unavailable.")
            return

        # Make room on band if needed
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
            print(f"  Slot {target} was just taken by another client on the band.")
            safe_release(hotel, "hotel", target)
            # prompt on failure
            if attempt < MAX_RETRIES:
                ans = input(f"  Keep searching for the next earliest slot? [y/n]: ").strip().lower()
                if ans not in ("y", "yes"):
                    print("  Search cancelled. Returning to menu.")
                    return
                wait = DELAY * (2 ** (attempt - 1))
                print(f"  Waiting {wait:.0f}s before next attempt...")
                time.sleep(wait)
            continue
        except ReservationLimitError:
            print("  You are already holding the maximum of 2 band reservations.")
            print(f"  Releasing hotel slot {target} - use option 7 to clean up, then try again.")
            safe_release(hotel, "hotel", target)
            return
        except Exception:
            print("  The band reservation did not go through - "
                  "the server may be temporarily unavailable.")
            safe_release(hotel, "hotel", target)
            return

        # ── Both confirmed - success ──────────────────────────────────────────
        print(f"\n  Slot {target} is now confirmed on both hotel and band.")

        #  release ALL other reservations on both services
        _release_all_except(target, hotel_held, band_held)

        status.update([target], [target])
        elapsed = time.time() - t0
        print(f"\n  Completed in {elapsed:.1f}s across {attempt_used} attempt(s).")
        return
        
    elapsed = time.time() - t0
    print(f"  Could not secure a matching booking after {MAX_RETRIES} attempts "
          f"({elapsed:.1f}s elapsed).")
    if current_best:
        print(f"  Your existing booking at slot {current_best} is still active.")


def _release_all_except(confirmed_slot: int, hotel_held: list, band_held: list):
    """
    Release every reservation on both services except the confirmed slot.

    Called after a successful booking to ensure exactly one clean pair
    remains. Runs parallel releases for any slot held on both services.

    Args:
        confirmed_slot: The slot to keep.
        hotel_held:     All hotel slots held at time of booking.
        band_held:      All band slots held at time of booking.
    """
    to_drop_hotel = [s for s in hotel_held if s != confirmed_slot]
    to_drop_band  = [s for s in band_held  if s != confirmed_slot]

    if not to_drop_hotel and not to_drop_band:
        return

    print("\n  Releasing all other reservations to leave exactly one confirmed pair...")
    all_stray = sorted(set(to_drop_hotel) | set(to_drop_band))
    for slot in all_stray:
        h = slot in to_drop_hotel
        b = slot in to_drop_band
        if h and b:
            print(f"  {TAG_THREADED} Releasing slot {slot} from hotel and band simultaneously...")
            run_both(
                lambda s=slot: safe_release(hotel, "hotel", s),
                lambda s=slot: safe_release(band,  "band",  s),
            )
        elif h:
            print(f"  Releasing hotel slot {slot}...")
            safe_release(hotel, "hotel", slot)
        else:
            print(f"  Releasing band slot {slot}...")
            safe_release(band, "band", slot)