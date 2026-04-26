#!/usr/bin/env python3
"""
Wrapper around ThreadPoolExecutor for running one hotel call and one
band call at the same time.

Usage:
    hotel_result, band_result = run_both(
        lambda: hotel.get_slots_available(),
        lambda: band.get_slots_available(),
    )
"""

from concurrent.futures import ThreadPoolExecutor


def run_both(fn_hotel, fn_band) -> tuple:
    """
    Run fn_hotel and fn_band concurrently in separate threads.

    Both are submitted immediately and run in parallel. Results
    are returned as a (hotel_result, band_result) tuple once both finish.

    If either callable raises, the exception propagates from this function.
    The other thread still runs to completion first (the executor waits for
    all futures on exit), so we never leave a half-done operation in flight.

    Args:
        fn_hotel: Zero-argument function that performs the hotel API operation.
        fn_band:  Zero-argument function that performs the band API operation.

    Returns:
        Tuple of (hotel_result, band_result) where each element is whatever
        the corresponding function returned.

    Raises:
        Any exception raised by fn_hotel or fn_band.
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_hotel = executor.submit(fn_hotel)
        future_band  = executor.submit(fn_band)
        hotel_result = future_hotel.result()
        band_result  = future_band.result()
    return hotel_result, band_result