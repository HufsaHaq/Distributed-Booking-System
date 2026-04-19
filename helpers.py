"""
helpers
~~~~~~~
Small utility functions shared across the application.

These deal with the mechanics of slot management (parsing API responses,
releasing reservations safely, making room when at the 2-slot limit) so
the action functions in actions.py can stay focused on user-facing logic.
"""

import reservationapi
from cache import clear_cache


def slot_ids(raw_slots: list) -> list:
    """Convert raw API slot objects ([{"id": "14"}, ...]) to sorted integers."""
    return sorted(int(s["id"]) for s in raw_slots)


def safe_release(api: reservationapi.ReservationApi, service: str, slot_id: int):
    """
    Cancel a slot and report the outcome clearly.

    Prints success or failure rather than letting exceptions silently
    bubble up. Clears the availability cache on success so the next
    fetch reflects the released slot.
    """
    try:
        api.release_slot(slot_id)
        clear_cache()
        print(f"  {service.title()} slot {slot_id} cancelled.")
    except Exception as e:
        print(f"  Could not cancel {service} slot {slot_id}: {e}")


def free_up_slot(api: reservationapi.ReservationApi,
                 service: str,
                 held: list,
                 other_held: list) -> bool:
    """
    Release one unmatched slot to stay within the 2-reservation limit.

    Picks the highest-numbered unmatched slot (so we keep the smallest,
    most valuable slots). Returns True if a slot was freed, False if all
    held slots are part of a matched pair and nothing can be safely dropped.

    Args:
        api:        The service API instance to release from.
        service:    'hotel' or 'band', used only for display.
        held:       Slots currently held on this service.
        other_held: Slots held on the other service (used to spot matches).
    """
    unmatched = [s for s in held if s not in other_held]
    if not unmatched:
        print(f"  {service.title()} is at the 2-reservation limit and every "
              "held slot is part of a confirmed pair. Cannot make room without "
              "losing a confirmed booking.")
        return False

    to_drop = max(unmatched)  # drop the worst (highest) unmatched slot
    print(f"  {service.title()} is at the reservation limit. "
          f"Releasing unmatched {service} slot {to_drop} to make room...")
    try:
        api.release_slot(to_drop)
        clear_cache()
        print(f"  {service.title()} slot {to_drop} released.")
        return True
    except Exception as e:
        print(f"  Could not release {service} slot {to_drop}: {e}")
        return False
