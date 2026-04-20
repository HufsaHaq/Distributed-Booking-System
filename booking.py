#!/usr/bin/env python3
"""
booking

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


def show_menu():
    print()
    print(PINK + "=" * 55 + RESET)
    print(BOLD + PINK + "          Wedding Planner - Booking Menu" + RESET)
    print(PINK + "=" * 55 + RESET)
    print(f"  {BOLD}Status:{RESET} {WHITE}{status.get()}{RESET}")
    print(PINK + "-" * 55 + RESET)
    print(GREEN + "  1." + WHITE + "  View your current reservations"          + RESET)
    print(GREEN + "  2." + WHITE + "  View first 20 available slots"            + RESET)
    print(GREEN + "  3." + WHITE + "  Book a specific slot"                     + RESET)
    print(GREEN + "  4." + WHITE + "  Cancel a reservation"                     + RESET)
    print(GREEN + "  5." + WHITE + "  View first 5 slots free on both services" + RESET)
    print(GREEN + "  6." + WHITE + "  Reserve the earliest matching slot"       + RESET)
    print(GREEN + "  7." + WHITE + "  Cancel all unnecessary reservations"      + RESET)
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


def main():
    print(BOLD + PINK + "\nWelcome to the Wedding Planner Booking System." + RESET)
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
            os.system("clear")
            continue

        action = MENU_ACTIONS.get(choice)
        if action:
            try:
                action()
            except KeyboardInterrupt:
                print("\nAction interrupted. Returning to menu.")
            except Exception as e:
                print(f"\nSomething went wrong: {e}")
                print("Returning to the menu - no changes were made on the server.")
        else:
            print("  Please enter a number between 1 and 9.")


if __name__ == "__main__":
    main()
