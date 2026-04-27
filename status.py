#!/usr/bin/env python3
"""
Tracks the last-known reservation state so the menu can display a summary
line without making any API calls on every refresh.

Any action that learns the current holdings calls update() at the end.
The menu calls get() for the summary string, and get_holdings() for the
raw lists to display the per-service breakdown.
"""

_status: str = "Not checked yet - select option 1 to view your reservations."
_hotel_held: list = []
_band_held:  list = []


def update(hotel_held: list, band_held: list) -> None:
    """
    Compute and store a status summary from the current holdings.

    Args:
        hotel_held: List of slot IDs currently held on the hotel service.
        band_held:  List of slot IDs currently held on the band service.

    Returns:
        None.
    """
    global _status, _hotel_held, _band_held
    _hotel_held = sorted(hotel_held)
    _band_held  = sorted(band_held)

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
    """
    Return the current status summary string.

    Returns:
        A human-readable string describing the last-known reservation state.
    """
    return _status


def get_holdings() -> tuple:
    """
    Return the raw last-known held slot lists for hotel and band.

    Used by the menu to display per-service holdings without an API call.

    Returns:
        Tuple of (hotel_held, band_held) as sorted lists of ints.
        Both lists are empty if update() has not been called yet.
    """
    return _hotel_held, _band_held
