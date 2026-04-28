#!/usr/bin/env python3
"""
Reservation-cancelling menu actions - options 4 and 7.

Option 4 lets the user manually pick a slot to cancel.
Option 7 automatically drops everything except the best confirmed pair.

Both options ask for confirmation before making any destructive API call,
so cannot accidentally lose a confirmed booking.
"""

from clients  import hotel, band
from helpers  import get_held, get_held_with_retry, safe_release
from parallel import run_both
from colours  import TAG_THREADED, PINK, YELLOW, CYAN, RESET, BOLD
import status


def _confirm(prompt: str) -> bool:
    """
    Ask the user to confirm a destructive action.

    Args:
        prompt: The confirmation question to display.

    Returns:
        True if the user typed 'y' or 'yes', False for anything else.
    """
    answer = input(f"\n  {YELLOW}{prompt} [y/n]: {RESET}").strip().lower()
    return answer in ("y", "yes")


def cancel_booking() -> None:
    """
    Let the user cancel a reservation on the hotel, band, or both.

    Asks which service(s) to cancel on first, then shows only the slots
    held on that service, then asks for the slot number. This avoids
    showing irrelevant slots and makes the flow feel more natural.

    Returns:
        None. Prints results directly to stdout.
    """
    print("\nCancel a reservation")

    try:
        print(f"  {TAG_THREADED} Querying hotel and band held slots simultaneously...")
        hotel_held, band_held = run_both(
            lambda: get_held("hotel", hotel),
            lambda: get_held("band",  band),
        )
    except Exception:
        print("  Could not retrieve your reservations - the server may be temporarily unavailable. Please try again.")
        return

    if not hotel_held and not band_held:
        print("  You have no reservations to cancel.")
        return

    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots) if slots else "none"

    print(f"\n  {CYAN}{BOLD}Hotel{RESET} slots held: {fmt(hotel_held)}")
    print(f"  {YELLOW}{BOLD}Band {RESET} slots held: {fmt(band_held)}")

    # Step 1: ask which service(s) first
    print()
    service_choice = input(
        "  Cancel on hotel, band, or both? (or press Enter to go back): "
    ).strip().lower()

    if not service_choice:
        print("  Cancelled.")
        return

    on_hotel = service_choice in ("hotel", "both")
    on_band  = service_choice in ("band",  "both")

    if not on_hotel and not on_band:
        print("  Please enter 'hotel', 'band', or 'both'.")
        return

    # Step 2: show relevant slots and ask for the slot number
    if on_hotel and on_band:
        relevant = sorted(set(hotel_held) | set(band_held))
        print(f"\n  Slots available to cancel: {fmt(relevant)}")
    elif on_hotel:
        if not hotel_held:
            print("  You have no hotel reservations to cancel.")
            return
        print(f"\n  Hotel slots you hold: {fmt(hotel_held)}")
    else:
        if not band_held:
            print("  You have no band reservations to cancel.")
            return
        print(f"\n  Band slots you hold: {fmt(band_held)}")

    raw = input("\n  Enter the slot number to cancel (or press Enter to go back): ").strip()
    if not raw:
        print("  Cancelled.")
        return

    try:
        slot_id = int(raw)
    except ValueError:
        print(f"  '{raw}' is not a valid slot number.")
        return

    # Validate against the chosen service(s)
    if on_hotel and slot_id not in hotel_held:
        print(f"  You do not hold hotel slot {slot_id}. Hotel slots: {fmt(hotel_held)}")
        if not on_band:
            return
        on_hotel = False  # only had hotel in mind but slot isn't there

    if on_band and slot_id not in band_held:
        print(f"  You do not hold band slot {slot_id}. Band slots: {fmt(band_held)}")
        on_band = False

    if not on_hotel and not on_band:
        print(f"  You do not hold slot {slot_id} on the requested service(s).")
        return

    # Confirm before doing anything destructive
    targets = []
    if on_hotel:
        targets.append(f"hotel slot {slot_id}")
    if on_band:
        targets.append(f"band slot {slot_id}")
    target_str = " and ".join(targets)

    if not _confirm(f"Cancel {target_str}?"):
        print("  Cancelled - nothing was changed.")
        return

    if on_hotel and on_band:
        print(f"  {TAG_THREADED} Cancelling slot {slot_id} on hotel and band simultaneously...")
        run_both(
            lambda: safe_release(hotel, "hotel", slot_id),
            lambda: safe_release(band,  "band",  slot_id),
        )
    elif on_hotel:
        print(f"  Cancelling hotel slot {slot_id}...")
        safe_release(hotel, "hotel", slot_id)
    else:
        print(f"  Cancelling band slot {slot_id}...")
        safe_release(band, "band", slot_id)

    remaining_hotel = [s for s in hotel_held if not (on_hotel and s == slot_id)]
    remaining_band  = [s for s in band_held  if not (on_band  and s == slot_id)]
    status.update(remaining_hotel, remaining_band)


def cancel_unneeded() -> None:
    """
    Release everything except the earliest confirmed matched pair.

    A reservation is only 'needed' if it belongs to the lowest-numbered slot
    that is confirmed on both hotel and band. Everything else is dropped.
    Asks for confirmation before making any destructive call.
    Matched-pair releases run in parallel to halve the wait time.

    Returns:
        None. Prints results directly to stdout.
    """
    print("\nChecking for unnecessary reservations...")

    try:
        print(f"  {TAG_THREADED} Querying hotel and band held slots simultaneously...")
        hotel_held, band_held = run_both(
            lambda: get_held("hotel", hotel),
            lambda: get_held("band",  band),
        )
    except Exception as e:
        print("  Could not retrieve your reservations - the server may be temporarily unavailable. Please try again.")
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

    print(f"  Keeping slot {best_match} - confirmed on both hotel and band.")

    to_drop_hotel = [s for s in hotel_held if s != best_match]
    to_drop_band  = [s for s in band_held  if s != best_match]

    if not to_drop_hotel and not to_drop_band:
        print(f"  Nothing to cancel - slot {best_match} is your only booking "
              "and it is already confirmed on both services.")
        status.update(hotel_held, band_held)
        return

    # Show the user exactly what will be kept and what will be dropped
    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots) if slots else "none"

    print(f"\n  {BOLD}Will keep:{RESET}  slot {best_match} (confirmed on hotel + band)")
    if to_drop_hotel:
        print(f"  {BOLD}Will drop:{RESET}  hotel - {fmt(to_drop_hotel)}")
    if to_drop_band:
        print(f"  {BOLD}Will drop:{RESET}  band  - {fmt(to_drop_band)}")

    if not _confirm("Proceed with cancellation?"):
        print("  Cancelled - nothing was changed.")
        return

    all_stray = sorted(set(to_drop_hotel) | set(to_drop_band))
    for slot in all_stray:
        h = slot in to_drop_hotel
        b = slot in to_drop_band
        if h and b:
            print(f"  {TAG_THREADED} Releasing slot {slot} on hotel and band simultaneously...")
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

    print(f"\n  Done. Slot {best_match} is your confirmed booking on both services.")
    status.update([best_match], [best_match])