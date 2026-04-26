#!/usr/bin/env python3
"""

Utility functions shared across the application.

These deal with the mechanics of slot management (parsing API responses,
releasing reservations safely, retrying held-slot queries, and making room
when at the 2-slot limit) so the action functions can stay focused on
user-facing logic.
"""

import time
import reservationapi
from cache      import clear_cache, clear_service_cache
from exceptions import NotProcessedError


def _get_delay_and_retries():
    from clients import MAX_RETRIES, DELAY
    return MAX_RETRIES, DELAY


def slot_ids(raw_slots: list) -> list:
    """
    Convert raw API slot objects to a sorted list of integers.

    Args:
        raw_slots: List of dicts from the API, e.g. [{"id": "14"}, {"id": "15"}].

    Returns:
        Sorted list of slot IDs as integers, e.g. [14, 15].
    """
    return sorted(int(s["id"]) for s in raw_slots)


def get_held_with_retry(api: reservationapi.ReservationApi, service: str) -> list:
    """
    Fetch currently held slots, retrying on 404 (NotProcessedError).

    The spec notes that requests may not be processed in the order they are
    received. A 404 on get_slots_held() can legitimately occur right after
    a reservation is made if the server has not yet processed it. Rather than
    propagating that error, we retry with exponential backoff up to MAX_RETRIES
    times - doubling the wait on each attempt to reduce server load.

    Args:
        api:     The ReservationApi instance to query.
        service: Display name of the service ('hotel' or 'band'), used for
                 messages only.

    Returns:
        Sorted list of held slot IDs as integers.

    Raises:
        NotProcessedError: If the server returns 404 on every attempt.
        Any other exception raised by the API on non-404 errors.
    """
    from colours import TAG_RETRY
    MAX_RETRIES, DELAY = _get_delay_and_retries()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return slot_ids(api.get_slots_held())
        except NotProcessedError:
            if attempt < MAX_RETRIES:
                # Exponential backoff: the server may still be processing a
                # recent reservation - wait progressively longer before retrying.
                wait = DELAY * (2 ** (attempt - 1))
                print(f"  {TAG_RETRY} The {service} server has not finished "
                      f"processing the last request. "
                      f"Retrying in {wait:.0f}s "
                      f"(attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise


def safe_release(api: reservationapi.ReservationApi, service: str, slot_id: int) -> bool:
    """
    Cancel a slot and report the outcome clearly.

    Prints success or failure rather than letting exceptions bubble up silently.
    Clears the availability cache on success so the next fetch reflects the
    released slot.

    Args:
        api:     The ReservationApi instance to call (hotel or band).
        service: Display name of the service ('hotel' or 'band').
        slot_id: The slot number to release.

    Returns:
        True if the slot was released successfully, False otherwise.
    """
    try:
        api.release_slot(slot_id)
        clear_service_cache(service)
        print(f"  {service.title()} slot {slot_id} cancelled successfully.")
        return True
    except Exception as e:
        print(f"  Could not cancel {service} slot {slot_id} - the server may be temporarily unavailable.")
        return False


def free_up_slot(api: reservationapi.ReservationApi,
                 service: str,
                 held: list,
                 other_held: list) -> bool:
    """
    Release one unmatched slot to stay within the 2-reservation limit.

    Picks the highest-numbered unmatched slot to drop, so we keep the
    smallest (most valuable) slots. Refuses to drop a slot that is part
    of a confirmed matched pair.

    Args:
        api:        The ReservationApi instance to release from.
        service:    Display name of the service ('hotel' or 'band').
        held:       Slots currently held on this service.
        other_held: Slots held on the other service, used to identify matches.

    Returns:
        True if a slot was freed successfully, False if nothing could be dropped.
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
        clear_service_cache(service)
        print(f"  {service.title()} slot {to_drop} released.")
        return True
    except Exception as e:
        print(f"  Could not release {service} slot {to_drop} - the server may be temporarily unavailable.")
        return False
