#!/usr/bin/env python3
"""
Tracks the last-known reservation state so the menu can display a summary
line without making any API calls on every refresh.

Any action that learns the current holdings (view, book, cancel) calls
update() at the end. The menu just calls get() to read the stored string.
"""

_status: str = "Not checked yet - select option 1 to view your reservations."


def update(hotel_held: list, band_held: list):
    """
    Compute a summary string from the current holdings and store it.

    Call this whenever an action fetches the current slot holdings so the
    menu always reflects the most recent known state.
    """
    global _status

    matched    = sorted(set(hotel_held) & set(band_held))
    only_hotel = [s for s in hotel_held if s not in band_held]
    only_band  = [s for s in band_held  if s not in hotel_held]

    if matched:
        best = matched[0]
        extras = []
        if only_hotel:
            extras.append(f"unmatched hotel: {', '.join(map(str, only_hotel))}")
        if only_band:
            extras.append(f"unmatched band: {', '.join(map(str, only_band))}")
        suffix = f"  |  {', '.join(extras)}" if extras else ""
        _status = f"Best confirmed booking: Slot {best} (hotel + band){suffix}"
    elif hotel_held or band_held:
        parts = []
        if hotel_held:
            parts.append(f"hotel: {', '.join(map(str, hotel_held))}")
        if band_held:
            parts.append(f"band: {', '.join(map(str, band_held))}")
        _status = f"No confirmed match yet  |  Held - {', '.join(parts)}"
    else:
        _status = "No reservations held"


def get() -> str:
    """Return the current status summary string."""
    return _status