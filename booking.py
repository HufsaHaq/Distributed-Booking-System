#!/usr/bin/env python3
"""
Wedding Planner - main entry point.

Runs the menu loop. All business logic lives in actions.py; all API
setup lives in clients.py. This file just wires the menu together and
handles startup.
"""

import os
import sys

from view_actions    import view_current_bookings, view_available_slots, view_matching_slots
from booking_actions import book_specific_slot, reserve_earliest_match
from cancel_actions  import cancel_booking, cancel_unneeded
from cache           import cache_ages, CACHE_MAX_AGE_SECONDS
import status

# ANSI colour codes
PINK  = "\033[35m"
GREEN = "\033[32m"
WHITE = "\033[37m"
CYAN  = "\033[36m"
RESET = "\033[0m"
BOLD  = "\033[1m"


YELLOW = "\033[33m"


def _cache_hint() -> str:
    """One-line cache status shown at the bottom of the menu."""
    ages = cache_ages()
    parts = []
    for service, age in ages.items():
        if age is None:
            parts.append(f"{service}: no cache")
        elif age < CACHE_MAX_AGE_SECONDS:
            remaining = CACHE_MAX_AGE_SECONDS - age
            parts.append(f"{service}: cached ({remaining}s left)")
        else:
            parts.append(f"{service}: cache expired")
    return CYAN + "  Cache - " + " | ".join(parts) + RESET


def _holdings_display() -> str:
    """
    Build a two-line holdings summary from the last-known state in status.py.

    Reads from the stored lists - zero API calls. Returns an empty string
    if update() has not been called yet (startup before first check).

    Returns:
        A formatted string showing hotel and band slots, or '' if unknown.
    """
    hotel_held, band_held = status.get_holdings()
    if not hotel_held and not band_held:
        return ""

    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots) if slots else "none"

    matched    = sorted(set(hotel_held) & set(band_held))
    only_hotel = [s for s in hotel_held if s not in band_held]
    only_band  = [s for s in band_held  if s not in hotel_held]

    hotel_str = fmt(hotel_held)
    band_str  = fmt(band_held)

    lines = []
    lines.append(
        f"  {CYAN}{BOLD}Hotel{RESET} ({len(hotel_held)}/2): {WHITE}{hotel_str}{RESET}  "
        f"{YELLOW}{BOLD}Band{RESET} ({len(band_held)}/2): {WHITE}{band_str}{RESET}"
    )
    if matched:
        lines.append(f"  {GREEN}{BOLD}Confirmed match:{RESET} {WHITE}Slot(s) {fmt(matched)}{RESET}")
    if only_hotel:
        lines.append(f"  {CYAN}Hotel only (unmatched):{RESET} {fmt(only_hotel)}")
    if only_band:
        lines.append(f"  {YELLOW}Band only  (unmatched):{RESET} {fmt(only_band)}")
    return "\n".join(lines)


def show_menu():
    os.system("clear")
    print(PINK + "=" * 55 + RESET)
    print(BOLD + PINK + "          Wedding Planner - Booking Menu" + RESET)
    print(PINK + "=" * 55 + RESET)

    # Holdings block - permanent, reads from status (no API call)
    holdings = _holdings_display()
    if holdings:
        print(holdings)
        print(PINK + "-" * 55 + RESET)

    print(f"  {BOLD}Status:{RESET} {WHITE}{status.get()}{RESET}")
    print(PINK + "-" * 55 + RESET)
    print(GREEN + "  1." + WHITE + "  View your current reservations"          + RESET)
    print(GREEN + "  2." + WHITE + "  View first 20 available slots"            + RESET)
    print(GREEN + "  3." + WHITE + "  Book a specific slot"                     + RESET)
    print(GREEN + "  4." + WHITE + "  Cancel a reservation"                     + RESET)
    print(GREEN + "  5." + WHITE + "  View first 5 slots free on both services" + RESET)
    print(GREEN + "  6." + WHITE + "  Reserve the earliest matching slot"       + RESET)
    print(GREEN + "  7." + WHITE + "  Cancel any unneeded reservations"         + RESET)
    print(PINK + "-" * 55 + RESET)
    print(GREEN + "  8." + WHITE + "  Clear screen"                             + RESET)
    print(GREEN + "  9." + WHITE + "  Exit"                                     + RESET)
    print(PINK + "=" * 55 + RESET)
    print(_cache_hint())


MENU_ACTIONS = {
    "1": view_current_bookings,
    "2": view_available_slots,
    "3": book_specific_slot,
    "4": cancel_booking,
    "5": view_matching_slots,
    "6": reserve_earliest_match,
    "7": cancel_unneeded,
}


def _pause() -> None:
    """
    Wait for the user to press Enter before the menu redraws.

    This gives the user (and the marker) time to read the output from the
    previous action before it scrolls away. Typing '9' exits immediately
    without going back through the menu.

    Returns:
        None.
    """
    print()
    print(PINK + "─" * 55 + RESET)
    try:
        ans = input(WHITE + "  Press Enter to return to menu  (or 9 to exit): " + RESET).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        sys.exit(0)
    if ans == "9":
        print(PINK + "\nGoodbye. Good luck with the wedding!" + RESET)
        sys.exit(0)


def main():
    print(BOLD + PINK + "\n" + "=" * 55 + RESET)
    print(BOLD + PINK + "   Wedding Planner - Distributed Booking System" + RESET)
    print(PINK + "=" * 55 + RESET)
    print(WHITE +
          "  Coordinates hotel and band reservations via two\n"
          "  independent REST APIs, competing in real time with\n"
          "  other clients for the earliest available slot.\n" + RESET)
    print(f"  {CYAN}Slots:{RESET}   1–550  (slot 1 = earliest date)")
    print(f"  {CYAN}Limit:{RESET}   2 reservations per service at once")
    print(f"  {CYAN}Goal:{RESET}    same slot confirmed on hotel AND band")
    print(PINK + "-" * 55 + RESET)
    print(BOLD + WHITE + "  Implemented features:" + RESET)
    print(WHITE + "  + Caching          " + RESET + "Available & held slots cached in memory")
    print(WHITE + "  + Threading        " + RESET + "Hotel & band API calls run in parallel")
    print(WHITE + "  + Exponential backoff " + RESET + "Retry waits double on each attempt")
    print(WHITE + "  + Smart limit handling " + RESET + "Auto-upgrades if a better slot is found")
    print(WHITE + "  + Auto-cleanup     " + RESET + "Stray reservations cleared after booking")
    print(WHITE + "  + 404 retry logic  " + RESET + "Handles out-of-order server processing")
    print(WHITE + "  + Targeted cache   " + RESET + "Only clears the service that changed")
    print(WHITE + "  + Coloured output  " + RESET + "[LIVE] [CACHED] [THREADED] [WARNING] tags")
    print(PINK + "=" * 55 + RESET)
    print()
    print("Checking your existing reservations on startup...")
    view_current_bookings()

    while True:
        show_menu()

        try:
            choice = input(PINK + "\nChoose an option (1–9): " + RESET).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            sys.exit(0)

        if choice == "9":
            print(PINK + "\nGoodbye. Good luck with the wedding!" + RESET)
            sys.exit(0)

        if choice == "8":
            continue   # show_menu() at top of loop already clears

        action = MENU_ACTIONS.get(choice)
        if action:
            try:
                action()
            except KeyboardInterrupt:
                print("\nAction interrupted. Returning to menu.")
            except Exception as e:
                print(f"\nSomething went wrong: {e}")
                print("Returning to the menu - no changes were made on the server.")
            _pause()
        else:
            print("  Please enter a number between 1 and 9.")


if __name__ == "__main__":
    main()
