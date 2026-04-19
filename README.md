# Wedding Planner - Booking System

A command-line client for coordinating hotel and band reservations for a wedding.
It talks to two separate REST APIs and makes sure both are booked on the same slot number.



## How to run

```bash
python3 booking.py

or

chmod +x booking.py
./booking.py
```



## File structure

```
booking.py           ← Run this. Entry point and menu loop.
view_actions.py      ← Menu options 1, 2, 5  (read-only, nothing gets changed)
booking_actions.py   ← Menu options 3, 6     (creates reservations)
cancel_actions.py    ← Menu options 4, 7     (cancels reservations)
clients.py           ← Loads config and creates the hotel/band API objects
cache.py             ← Short-term cache for available slot lists
helpers.py           ← Small utilities shared across the action files
reservationapi.py    ← Low-level HTTP wrapper (provided, handles retries + delays)
exceptions.py        ← Custom exceptions for API error codes (provided)
api.ini              ← API URLs and keys
```



## What each file does

### `booking.py`
The entry point. Displays the menu, reads the user's choice, and calls the
right function. 

On startup it automatically shows your current reservations.

This file just wires the menu numbers to the functions in the action files.

### `view_actions.py`

- **Option 1 - View current reservations:** Fetches what you currently hold
  on both hotel and band, then sorts them into confirmed pairs (same slot on
  both) and unmatched ones (only on one service).

- **Option 2 - View first 20 available slots:** Hits both APIs fresh and
  shows the first 20 free slots on each. Updates the cache.

- **Option 5 - View first 5 matching slots:** Finds slots that are free on
  both hotel *and* band simultaneously, and shows the earliest five. Uses the
  cache if the data is recent enough, to avoid unnecessary API calls.

### `booking_actions.py`
Everything that creates a reservation.

- **Option 3 - Book a specific slot:** Takes a slot number from the user and
  reserves it on both hotel and band. Books the hotel first; if the band then
  fails, it releases the hotel slot automatically so nothing is left dangling.

- **Option 6 - Reserve the earliest matching slot:**  Finds the lowest slot number currently free on both services and
  books it. Key behaviours:
  - If you already have a confirmed pair, it only books a new one if it finds
    something earlier - otherwise it tells you your current booking is already
    optimal.
  - Retries up to the configured retry limit if no matching slots are visible
    right now.
  - If it successfully books a better slot, it releases the old confirmed pair
    only after the new one is secured - so never left with nothing.
  - Automatically cleans up any stray single-service reservations afterwards.

### `cancel_actions.py`
Everything that removes a reservation.

- **Option 4 - Cancel a specific reservation:** Shows what you currently hold,
  asks for a slot number, then lets you cancel it on the hotel, band, or both.

- **Option 7 - Cancel all unnecessary reservations:** Keeps only the earliest
  confirmed pair (same slot on both services) and releases everything else.
  This is also run automatically after a successful Option 6.

### `clients.py`
Loads `api.ini` and creates the two `ReservationApi` instances (`hotel` and
`band`) that every action file imports. Also has `MAX_RETRIES` and `DELAY`
so the action files don't need to re-parse the config themselves. 

### `cache.py`
Fetching available-slot lists fresh on every single operation would be wasteful and unnecessary. 
This module stores the last-fetched list for each service and serves it from memory for up to 30
seconds. It always tells you in the output whether you're seeing live or cached
data. Any operation that is about to make a booking always bypasses the cache
(`force_fresh=True`) to make sure it's working with current data.

### `helpers.py`

- `slot_ids()` - converts the raw API response format (`[{"id": "14"}, ...]`) into a plain sorted list of integers.
- `safe_release()` - cancels a slot and prints a clear success or failure message, rather than letting exceptions go silently.
- `free_up_slot()` - when you're at the 2-reservation limit and need to book something new, this drops the highest-numbered *unmatched* slot to make room. It refuses to drop a slot that's part of a confirmed pair. Lower slot numbers are earlier dates, which are more desirable.

### `reservationapi.py` 
Handles adding the Authorization header to every
request, automatic retries on server errors (5xx), and raising the right
custom exception for each client error (4xx). Also enforces the 1-second
minimum delay between requests to avoid rate-limiting.

### `exceptions.py` 
Defines the custom exception classes that `reservationapi.py` raises, one per
HTTP error code: `BadRequestError` (400), `InvalidTokenError` (401),
`BadSlotError` (403), `NotProcessedError` (404), `SlotUnavailableError` (409),
`ReservationLimitError` (451).

### `api.ini`
Contains the base URLs and API keys for the hotel and band services, plus the
global retry count and delay. 
