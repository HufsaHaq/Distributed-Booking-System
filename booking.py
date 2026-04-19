#!/usr/bin/env python3
"""
booking

Wedding Planner - main entry point.

Runs the menu loop. All business logic lives in actions.py; all API
setup lives in clients.py. This file just wires the menu together and
handles startup.
"""

import sys

from view_actions    import view_current_bookings, view_available_slots, view_matching_slots
from booking_actions import book_specific_slot, reserve_earliest_match
from cancel_actions  import cancel_booking, cancel_unneeded


PINK   = "\033[95m"
GREEN  = "\033[92m"
WHITE  = "\033[97m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def show_menu():
    print()
    print(PINK + "=" * 47 + RESET)
    print(BOLD + PINK + "       Wedding Planner - Booking Menu" + RESET)
    print(PINK + "=" * 47 + RESET)

    print(GREEN + "  1." + WHITE + " View your current reservations" + RESET)
    print(GREEN + "  2." + WHITE + " View first 20 available slots" + RESET)
    print(GREEN + "  3." + WHITE + " Book a specific slot" + RESET)
    print(GREEN + "  4." + WHITE + " Cancel a reservation" + RESET)
    print(GREEN + "  5." + WHITE + " View first 5 slots free on both services" + RESET)
    print(GREEN + "  6." + WHITE + " Reserve the earliest matching slot" + RESET)
    print(GREEN + "  7." + WHITE + " Cancel all unnecessary reservations" + RESET)
    print(GREEN + "  8." + WHITE + " Exit" + RESET)

    print(PINK + "=" * 47 + RESET)


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
    print(PINK + BOLD + "\nWelcome to the Wedding Planner Booking System." + RESET)
    print("Checking your existing reservations on startup...")
    view_current_bookings()

    while True:
        show_menu()

        try:
            choice = input(PINK + "Choose an option (1–8): " + RESET).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            sys.exit(0)

        if choice == "8":
            print(PINK + "\nGoodbye. Good luck with the wedding!" + RESET)
            sys.exit(0)

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
            print("  Please enter a number between 1 and 8.")


if __name__ == "__main__":
    main()
