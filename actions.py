"""
actions
~~~~~~~
Implements the seven user-facing actions in the Wedding Planner menu.

Each function is self-contained: it fetches what it needs, does its work,
prints clear output, and handles errors gracefully. None of them crash the
program — failures are reported and control returns to the menu.
"""

import time

from exceptions import (
    BadRequestError, InvalidTokenError, BadSlotError, NotProcessedError,
    SlotUnavailableError, ReservationLimitError,
)
from requests.exceptions import HTTPError

from clients import hotel, band, MAX_RETRIES, DELAY
from cache   import get_available, clear_cache
from helpers import slot_ids, safe_release, free_up_slot


# ---------------------------------------------------------------------------
# 1. View current reservations
# ---------------------------------------------------------------------------

def view_current_bookings():
    """
    Show all slots currently held on hotel and band, with match status.

    Highlights confirmed pairs (same slot on both services) and lone
    reservations that still need a matching slot on the other service.
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
        print("  No confirmed match yet — you need the same slot on both services.")

    if only_hotel:
        print(f"  Hotel only (unmatched): {fmt(only_hotel)}")
    if only_band:
        print(f"  Band only  (unmatched): {fmt(only_band)}")


# ---------------------------------------------------------------------------
# 2. View first 20 available slots on each service
# ---------------------------------------------------------------------------

def view_available_slots():
    """
    Fetch live availability from both services and show the first 20 slots each.

    Always goes to the server (force_fresh=True) so the user gets current data.
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


# ---------------------------------------------------------------------------
# 3. Book a specific user-specified slot
# ---------------------------------------------------------------------------

def book_specific_slot():
    """
    Reserve a slot number chosen by the user on both hotel and band.

    Books the hotel first. If the hotel succeeds but the band then fails,
    the hotel reservation is released automatically so nothing is left dangling.
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
              f"Hotel slot {slot_id} was reserved but band was not — "
              "cancel a band reservation and try again.")
    except BadSlotError:
        print(f"  Slot {slot_id} does not exist on the band side.")
        print(f"  Releasing hotel slot {slot_id}...")
        safe_release(hotel, "hotel", slot_id)
    except Exception as e:
        print(f"  Band booking failed: {e}")
        print(f"  Releasing hotel slot {slot_id} to avoid a dangling reservation...")
        safe_release(hotel, "hotel", slot_id)


# ---------------------------------------------------------------------------
# 4. Cancel a reservation
# ---------------------------------------------------------------------------

def cancel_booking():
    """
    Let the user cancel a reservation on the hotel, band, or both.

    Shows current holdings first so the user knows what is available to cancel.
    """
    print("\nCancel a reservation")

    try:
        hotel_held = slot_ids(hotel.get_slots_held())
        band_held  = slot_ids(band.get_slots_held())
    except Exception as e:
        print(f"  Could not retrieve your reservations: {e}")
        return

    if not hotel_held and not band_held:
        print("  You have no reservations to cancel.")
        return

    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots) if slots else "none"

    print(f"\n  Hotel slots: {fmt(hotel_held)}")
    print(f"  Band  slots: {fmt(band_held)}")

    raw = input("\nEnter the slot number to cancel (or press Enter to go back): ").strip()
    if not raw:
        print("  Cancelled.")
        return

    try:
        slot_id = int(raw)
    except ValueError:
        print(f"  '{raw}' is not a valid slot number.")
        return

    on_hotel = slot_id in hotel_held
    on_band  = slot_id in band_held

    if not on_hotel and not on_band:
        print(f"  You do not hold slot {slot_id} on either service.")
        return

    if on_hotel and on_band:
        choice = input(
            f"  Slot {slot_id} is held on both services. "
            "Cancel on hotel, band, or both? [hotel/band/both]: "
        ).strip().lower()
        on_hotel = choice in ("hotel", "both")
        on_band  = choice in ("band",  "both")
        if not on_hotel and not on_band:
            print("  Unrecognised choice. Nothing cancelled.")
            return

    if on_hotel:
        print(f"  Cancelling hotel slot {slot_id}...")
        safe_release(hotel, "hotel", slot_id)

    if on_band:
        print(f"  Cancelling band slot {slot_id}...")
        safe_release(band, "band", slot_id)


# ---------------------------------------------------------------------------
# 5. View first 5 slots free on both services simultaneously
# ---------------------------------------------------------------------------

def view_matching_slots():
    """
    Show the 5 earliest slots currently free on both hotel and band.

    Uses the cache where available to reduce API calls — run option 2 first
    if you want to make sure the data is fully up to date.
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
        print("  Availability changes constantly — try again in a moment.")
        return

    print(f"\n  First 5 slots free on both services:")
    for slot in matching[:5]:
        print(f"    Slot {slot}")
    print(f"\n  ({len(matching)} matching slots available in total.)")


# ---------------------------------------------------------------------------
# 6. Reserve the earliest matching slot (with retry and upgrade logic)
# ---------------------------------------------------------------------------

def reserve_earliest_match():
    """
    Find the earliest slot free on both services and book it.

    Strategy:
      - Read your current holdings. If you already have a confirmed pair,
        that is your current best. We only book a new slot if we can
        improve on it (i.e. find a lower-numbered match).
      - Retry up to MAX_RETRIES times if no matching slots are available
        right now — availability changes as other clients release slots.
      - Once a new pair is confirmed, release the old matched pair and
        any other stray reservations automatically.
      - You are never left without at least one booking: the old pair
        is only released after the new one is secured.
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

    # Retry loop — the spec requires we don't give up just because no matching
    # slots are visible right now; availability shifts as other clients act.
    for attempt in range(1, MAX_RETRIES + 1):

        try:
            hotel_avail = get_available(hotel, "hotel", force_fresh=True)
            band_avail  = get_available(band,  "band",  force_fresh=True)
        except Exception as e:
            print(f"  Could not fetch availability (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {DELAY:.0f}s...")
                time.sleep(DELAY)
            continue

        matching = sorted(set(hotel_avail) & set(band_avail))

        if not matching:
            if attempt < MAX_RETRIES:
                print(f"  No matching slots available right now "
                      f"(attempt {attempt}/{MAX_RETRIES}). Retrying in {DELAY:.0f}s...")
                time.sleep(DELAY)
                continue
            else:
                print(f"  No matching slots found after {MAX_RETRIES} attempts.")
                if current_best:
                    print(f"  Your existing booking at slot {current_best} is still active.")
                return

        target = matching[0]
        print(f"  Earliest slot free on both: slot {target}.")

        if current_best is not None and target >= current_best:
            print(f"  Your current booking (slot {current_best}) is already the "
                  "earliest available match. Nothing to do.")
            return

        print(f"\n  Attempting to book slot {target}...")

        # Re-read holdings before each booking attempt — they may have changed
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

        # Both sides confirmed — success
        print(f"\n  Slot {target} is now confirmed on both hotel and band.")

        # Release the old confirmed pair now that the new one is secured
        if current_best is not None and current_best != target:
            print(f"  Releasing previous booking at slot {current_best}...")
            safe_release(hotel, "hotel", current_best)
            safe_release(band,  "band",  current_best)

        # Auto-clean any remaining stray reservations
        _auto_cancel_unneeded(target)
        return

    # Fell out of the loop without succeeding
    print(f"  Could not secure a matching booking after {MAX_RETRIES} attempts.")
    if current_best:
        print(f"  Your existing booking at slot {current_best} is still active.")


# ---------------------------------------------------------------------------
# 7. Cancel all unnecessary reservations
# ---------------------------------------------------------------------------

def cancel_unneeded():
    """
    Release everything except the earliest confirmed matched pair.

    A reservation is only 'needed' if it belongs to the lowest-numbered slot
    that is confirmed on both hotel and band. Everything else is dropped.
    """
    print("\nChecking for unnecessary reservations...")

    try:
        hotel_held = slot_ids(hotel.get_slots_held())
        band_held  = slot_ids(band.get_slots_held())
    except Exception as e:
        print(f"  Could not retrieve your reservations: {e}")
        return

    if not hotel_held and not band_held:
        print("  You have no reservations.")
        return

    matched    = sorted(set(hotel_held) & set(band_held))
    best_match = matched[0] if matched else None

    if best_match is None:
        print("  You do not have a confirmed matched pair yet.")
        print("  Use option 6 to find and book a matching slot before cleaning up.")
        return

    print(f"  Keeping slot {best_match} — confirmed on both hotel and band.")

    to_drop_hotel = [s for s in hotel_held if s != best_match]
    to_drop_band  = [s for s in band_held  if s != best_match]

    if not to_drop_hotel and not to_drop_band:
        print("  Nothing to cancel — your reservations are already tidy.")
        return

    for slot in to_drop_hotel:
        print(f"  Releasing hotel slot {slot}...")
        safe_release(hotel, "hotel", slot)

    for slot in to_drop_band:
        print(f"  Releasing band slot {slot}...")
        safe_release(band, "band", slot)

    print(f"\n  Done. Slot {best_match} is your confirmed booking on both services.")


# ---------------------------------------------------------------------------
# Internal helper — auto-cleanup after a successful reserve_earliest_match
# ---------------------------------------------------------------------------

def _auto_cancel_unneeded(confirmed_slot: int):
    """
    After a successful booking, silently drop any stray reservations.

    Called automatically by reserve_earliest_match once the new pair is
    secured. Option 7 still exists so markers can trigger this manually.
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
