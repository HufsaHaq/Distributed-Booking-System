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
parallel.py          ← Runs hotel and band API calls concurrently
status.py            ← Tracks current booking state for the menu status line
reservationapi.py    ← Low-level HTTP wrapper (provided - handles retries + delays)
exceptions.py        ← Custom exceptions for API error codes (provided)
api.ini              ← API URLs and keys 
```

---

## Menu options

| Option | What it does |
|--------|-------------|
| 1 | View your current reservations |
| 2 | View first 20 available slots on each service |
| 3 | Book a specific slot (submenu: hotel only / band only / both) |
| 4 | Cancel a reservation |
| 5 | View first 5 slots free on both services simultaneously |
| 6 | Reserve the earliest matching slot (with retry and auto-cleanup) |
| 7 | Cancel all unnecessary reservations |
| 8 | Clear screen |
| 9 | Exit |

---

## What each file does

### `booking.py`
The entry point. Displays the menu, reads the user's choice, and calls the
right function. 

On startup it automatically shows your current reservations.

The menu header shows two live pieces of information on every refresh:
- **Status line** - the last-known booking state (e.g. "Best confirmed booking: Slot 14 (hotel + band)"), updated after every action that touches reservations. Reads from `status.py` with no extra API calls.
- **Cache hint** - how many seconds remain before each service's cached slot list expires (e.g. "hotel: cached (22s left) | band: no cache"). Reads from `cache.py`.

---

### `view_actions.py`
**Option 1 - View current reservations**
Fetches what you hold on both hotel and band in parallel, then groups them into
confirmed pairs (same slot on both) and unmatched ones (only on one service).
Updates the status line afterwards.

**Option 2 - View first 20 available slots**
Always hits both servers fresh (bypasses the cache) and shows the first 20 free
slots on each. Updates the cache as a side effect so subsequent options that use
the cache start with fresh data.

**Option 5 - View first 5 matching slots**
Finds slots that are free on both hotel *and* band simultaneously and shows the
earliest five. Uses the cache if it is recent enough, to avoid unnecessary API
calls.

All three functions fetch from both services in parallel and print elapsed time.

### `booking_actions.py`
Everything that creates a reservation.

**Option 3 - Book a specific slot (submenu)**
Shows a secondary menu with three choices:
- *Book hotel only* - fetches and displays available hotel slots first, then reserves the slot you enter. Reminds you that a matching band slot is still needed.
- *Book band only* - same pattern for the band.
- *Book matching* - fetches and displays slots free on both services first, then reserves the slot you enter on hotel and then band. If the hotel succeeds but the band fails for any reason, the hotel slot is released automatically so nothing is left dangling.

**Option 6 - Reserve the earliest matching slot**
The main automated strategy. Key behaviours:
- Reads your current holdings first to find the current best confirmed pair.
- Retries up to the configured retry limit (`retries` in `api.ini`) if no matching slots are visible right now - availability changes constantly as other clients compete.
- Only books a new slot if it is earlier than your current best - if you already have the optimal slot it tells you and stops.
- If it successfully books a better slot, it releases the old confirmed pair *only after* the new one is secured.
- Automatically cleans up any remaining stray single-service reservations after a successful booking.
- Updates the status line on success.


### `cancel_actions.py`
Everything that removes a reservation.

**Option 4 - Cancel a specific reservation**
Shows your current holdings, asks for a slot number, then asks whether to cancel
it on hotel, band, or both. If cancelling both, the two release calls are made
in parallel.

**Option 7 - Cancel all unnecessary reservations**
Keeps only the earliest slot that is confirmed on both hotel and band, and
releases everything else. Matched-pair releases run in parallel. This is also
triggered automatically after a successful Option 6, but it is exposed here so
markers can trigger it manually at any time.


### `clients.py`
Loads `api.ini` and creates the two `ReservationApi` instances (`hotel` and `band`)
that every action file imports. Also exposes `MAX_RETRIES` and `DELAY` as
constants so the action files do not need to re-parse the config themselves.

Uses `inline_comment_prefixes=("##", "#")` when parsing the config so the `##`
comments in `api.ini` are not accidentally included in the key or URL values.

### `cache.py`
Fetching available-slot lists fresh on every operation would be wasteful and would
risk hitting the rate limit. This module stores the last-fetched list for each
service and serves it from memory for up to 30 seconds.

Every fetch prints one of two tags so the source is always visible:
- `[LIVE]` - data was fetched fresh from the server just now.
- `[CACHED]` - data is being served from memory, along with how old it is and
  how many seconds remain before it expires (e.g. `refreshes in 22s`).

Any operation that is about to make a booking always bypasses the cache
(`force_fresh=True`) to make sure it is working with current data.

Also exposes `cache_ages()` which `booking.py` uses to build the cache hint line
shown at the bottom of the menu.

### `helpers.py`

- `slot_ids()` - converts the raw API response format (`[{"id": "14"}, ...]`)
  into a plain sorted list of integers.
- `safe_release()` - cancels a slot and prints a clear success or failure message
  rather than letting exceptions bubble up silently. Clears the cache on success.
- `free_up_slot()` - when at the 2-reservation limit and needing to book something
  new, this drops the highest-numbered *unmatched* slot to make room. It refuses
  to drop a slot that forms part of a confirmed pair. Lower slot numbers are
  earlier dates and therefore more valuable, so we always sacrifice the highest.


### `parallel.py`
Provides a single function `run_both(fn_hotel, fn_band)` that submits both
callables to a `ThreadPoolExecutor(max_workers=2)` and returns
`(hotel_result, band_result)` once both finish.

This is safe because each thread only ever calls one service - there is never
more than one concurrent request to the same API, which satisfies the spec's
rate-limiting requirement.

Every place `run_both` is used prints a `[THREADED]` tag in the output so it is
visible when parallel execution is happening. The operations that use threading are:

- Fetching held slots from both services (options 1, 4, 6, 7 and auto-cleanup)
- Fetching available slots from both services (options 2, 3, 5 and inside option 6)
- Releasing a matched pair (hotel + band for the same slot) simultaneously

Without threading these operations would take roughly 2 seconds each (1 second
minimum per API call due to rate limiting). With threading they complete in
roughly 1 second.

### `status.py`
Stores the last-known reservation state as a short human-readable string.
`update(hotel_held, band_held)` computes a summary such as:

- `Best confirmed booking: Slot 14 (hotel + band)`
- `No confirmed match yet  |  Held - hotel: 14, band: 20`
- `No reservations held`

Any action that learns the current holdings calls `update()` before returning.
`booking.py` calls `get()` to display this in the menu - no extra API calls.


### `reservationapi.py` 
Handles adding the `Authorization: Bearer` header to
every request, automatic retries on server errors (5xx), and raising the
appropriate custom exception for each client error (4xx). Enforces a minimum
1-second delay between requests to respect the rate limit.

### `exceptions.py` 
Custom exception classes raised by `reservationapi.py`, one per HTTP error code:

| Exception | HTTP code | Meaning |
|-----------|-----------|---------|
| `BadRequestError` | 400 | Malformed request |
| `InvalidTokenError` | 401 | API key missing or wrong |
| `BadSlotError` | 403 | Slot number does not exist |
| `NotProcessedError` | 404 | Request not yet processed |
| `SlotUnavailableError` | 409 | Slot already taken by someone else |
| `ReservationLimitError` | 451 | Already holding the maximum of 2 reservations |

### `api.ini`
Contains the base URLs and API keys for the hotel and band services, plus the
global retry count and delay.
