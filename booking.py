"""
booking
~~~~~~~
Wedding Planner — main entry point.

Runs the menu loop. All business logic lives in actions.py; all API
setup lives in clients.py. This file just wires the menu together and
handles startup.
"""

import sys

from view_actions    import view_current_bookings, view_available_slots, view_matching_slots
from booking_actions import book_specific_slot, reserve_earliest_match
from cancel_actions  import cancel_booking, cancel_unneeded


def show_menu():
    print()
    print("=" * 47)
    print("       Wedding Planner — Booking Menu")
    print("=" * 47)
    print("  1.  View your current reservations")
    print("  2.  View first 20 available slots")
    print("  3.  Book a specific slot")
    print("  4.  Cancel a reservation")
    print("  5.  View first 5 slots free on both services")
    print("  6.  Reserve the earliest matching slot")
    print("  7.  Cancel all unnecessary reservations")
    print("  8.  Exit")
    print("=" * 47)


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
    print("\nWelcome to the Wedding Planner Booking System.")
    print("Checking your existing reservations on startup...")
    view_current_bookings()

    while True:
        show_menu()

        try:
            choice = input("Choose an option (1–8): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            sys.exit(0)

        if choice == "8":
            print("\nGoodbye. Good luck with the wedding!")
            sys.exit(0)

        action = MENU_ACTIONS.get(choice)
        if action:
            try:
                action()
            except KeyboardInterrupt:
                print("\nAction interrupted. Returning to menu.")
            except Exception as e:
                print(f"\nSomething went wrong: {e}")
                print("Returning to the menu — no changes were made on the server.")
        else:
            print("  Please enter a number between 1 and 8.")


if __name__ == "__main__":
    main()
