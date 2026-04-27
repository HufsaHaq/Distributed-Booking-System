#!/usr/bin/env python3
"""
Wedding Planner - main entry point.

Runs the menu loop. All business logic lives in the *_actions modules.
All API setup lives in clients.py. This file wires the menu together,
handles startup, and defines what the "home page" looks like.
"""

import os
import sys

from view_actions    import view_current_bookings, view_available_slots, view_matching_slots
from booking_actions import book_specific_slot, reserve_earliest_match
from cancel_actions  import cancel_booking, cancel_unneeded
from cache           import cache_ages, CACHE_MAX_AGE_SECONDS
import status

# ANSI colour codes - duplicated here so booking.py has no circular imports
PINK   = "\033[35m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
WHITE  = "\033[37m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _cache_hint() -> str:
    """One-line cache status for the bottom of the menu page."""
    ages = cache_ages()
    parts = []
    for service, age in ages.items():
        if age is None:
            parts.append(f"{service}: no cache")
        elif age < CACHE_MAX_AGE_SECONDS:
            parts.append(f"{service}: cached ({CACHE_MAX_AGE_SECONDS - age}s left)")
        else:
            parts.append(f"{service}: cache expired")
    return CYAN + "  Cache - " + " | ".join(parts) + RESET


def _holdings_display() -> str:
    """
    Build a holdings block from the last-known state in status.py.

    Zero API calls - reads from the stored lists that every action updates.
    Returns an empty string before the first reservation check.

    Returns:
        Formatted multi-line string, or '' if no holdings data yet.
    """
    hotel_held, band_held = status.get_holdings()
    if not hotel_held and not band_held:
        return ""

    def fmt(slots):
        return ", ".join(f"Slot {s}" for s in slots) if slots else "none"

    matched    = sorted(set(hotel_held) & set(band_held))
    only_hotel = [s for s in hotel_held if s not in band_held]
    only_band  = [s for s in band_held  if s not in hotel_held]

    lines = [
        f"  {CYAN}{BOLD}Hotel{RESET} ({len(hotel_held)}/2): {WHITE}{fmt(hotel_held)}{RESET}  "
        f"{YELLOW}{BOLD}Band{RESET}  ({len(band_held)}/2): {WHITE}{fmt(band_held)}{RESET}"
    ]
    if matched:
        lines.append(
            f"  {GREEN}{BOLD} Confirmed match:{RESET} {WHITE}Slot(s) {fmt(matched)}{RESET}"
        )
    if only_hotel:
        lines.append(f"  {CYAN}  Hotel only (unmatched):{RESET} {fmt(only_hotel)}")
    if only_band:
        lines.append(f"  {YELLOW}  Band only  (unmatched):{RESET} {fmt(only_band)}")
    return "\n".join(lines)


def _pause(prompt: str = "  Press Enter to return to menu  (or 9 to exit): ") -> None:
    """
    Wait for the user to press Enter so they can read the action output
    before the menu page redraws.

    Args:
        prompt: The line to display at the pause point.

    Returns:
        None. Exits the program if the user types '9'.
    """
    print()
    print(PINK + "─" * 55 + RESET)
    try:
        ans = input(WHITE + prompt + RESET).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        sys.exit(0)
    if ans == "9":
        print(PINK + "\nGoodbye. Good luck with the wedding!" + RESET)
        sys.exit(0)


# ── Menu page ──────────────────────────────────────────────────────────────────

def show_menu() -> None:
    """
    Clear the terminal and draw the full home page:
      - Compact banner (title + goal summary)
      - Current holdings (hotel and band slots, zero API calls)
      - Status line
      - Menu options
      - Cache hint

    This is the page the user always returns to after completing an action.
    """

    # ── Compact banner ────────────────────────────────────────────────────────
    print(PINK + "=" * 55 + RESET)
    print(BOLD + PINK + "   Wedding Planner - Distributed Booking System" + RESET)
    print(PINK + "-" * 55 + RESET)
    print(f"  {CYAN}Slots:{RESET} 1-550 (1 = earliest)  "
          f"{CYAN}Limit:{RESET} 2 per service")
    print(f"  {CYAN}Goal: {RESET} same slot confirmed on "
          f"{CYAN}hotel{RESET} AND {YELLOW}band{RESET}")
    print(PINK + "=" * 55 + RESET)

    # ── Holdings block ────────────────────────────────────────────────────────
    holdings = _holdings_display()
    if holdings:
        print(holdings)
        print(PINK + "-" * 55 + RESET)

    # ── Status + menu ─────────────────────────────────────────────────────────
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
    print(GREEN + "  8." + WHITE + "  Refresh / clear screen"                   + RESET)
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


# ── Startup ────────────────────────────────────────────────────────────────────

def _show_startup_banner() -> None:
    """
    Draw the full startup screen with the features list.

    Shown once at launch. The loop then takes over with show_menu() which
    includes a compact version of the banner so the user always has context.
    """
    os.system("clear")
    print(BOLD + PINK + "=" * 55 + RESET)
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
    print(f"  {GREEN}+{RESET} Caching           Available & held slots cached in memory")
    print(f"  {GREEN}+{RESET} Threading         Hotel & band API calls run in parallel")
    print(f"  {GREEN}+{RESET} Exponential backoff  Retry waits double on each attempt")
    print(f"  {GREEN}+{RESET} Smart limit handling Auto-upgrades if a better slot found")
    print(f"  {GREEN}+{RESET} Auto-cleanup       Stray reservations cleared after booking")
    print(f"  {GREEN}+{RESET} 404 retry logic    Handles out-of-order server processing")
    print(f"  {GREEN}+{RESET} Targeted cache     Only clears the service that changed")
    print(f"  {GREEN}+{RESET} Coloured output    [LIVE] [CACHED] [THREADED] [WARNING] tags")
    print(PINK + "=" * 55 + RESET)


def main():
    # Startup: show features banner, check current reservations, pause.
    _show_startup_banner()
    print()
    print("  Checking your existing reservations on startup...")
    print()
    view_current_bookings()
    _pause("  Press Enter to open the menu  (or 9 to exit): ")

    # Main loop: each iteration draws the full banner+menu page, runs the
    # chosen action, then pauses so the output can be read before redrawing.
    while True:
        _show_startup_banner()
        show_menu()

        try:
            choice = input(PINK + "\nChoose an option (1-9): " + RESET).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            sys.exit(0)

        if choice == "9":
            print(PINK + "\nGoodbye. Good luck with the wedding!" + RESET)
            sys.exit(0)

        if choice == "8":
            continue   # show_menu() at the top of the loop handles the clear

        action = MENU_ACTIONS.get(choice)
        if action:
            os.system("clear")
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