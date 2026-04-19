"""
cancel_actions
~~~~~~~~~~~~~~
Reservation-cancelling menu actions — options 4 and 7.

Option 4 lets the user manually pick a slot to cancel.
Option 7 automatically drops everything except the best confirmed pair.
"""

from clients import hotel, band
from helpers import slot_ids, safe_release


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


def cancel_unneeded():
    """
    Release everything except the earliest confirmed matched pair.

    A reservation is only 'needed' if it belongs to the lowest-numbered slot
    confirmed on both hotel and band. Everything else is dropped.
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
