# Wedding Planner - Booking System

A command-line client for coordinating hotel and band reservations for a wedding.
Talks to two independent REST APIs and ensures both are booked on the same slot number,
competing in real time with other clients for the earliest available date.

## How to run

```bash
python3 booking.py

or

chmod +x booking.py
./booking.py
```

## File structure

```
booking.py           - Run this. Entry point and menu loop.
view_actions.py      - Menu options 1, 2, 5  (read-only, nothing gets changed)
booking_actions.py   - Menu options 3, 6     (creates reservations)
cancel_actions.py    - Menu options 4, 7     (cancels reservations)
colours.py           - ANSI colour codes and output tags shared across all files
clients.py           - Loads config and creates the hotel/band API objects
cache.py             - Short-term cache for available slot lists
helpers.py           - Utilities: slot parsing, safe release, 404-retry logic
parallel.py          - Runs hotel and band API calls concurrently
status.py            - Tracks current booking state for the menu status line
reservationapi.py    - Low-level HTTP wrapper (provided — handles retries + delays)
exceptions.py        - Custom exceptions for API error codes (provided)
api.ini              - API URLs and keys (keep this private)
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
| 6 | Reserve the earliest matching slot (automated, with retry and auto-cleanup) |
| 7 | Cancel all unnecessary reservations |
| 8 | Clear screen |
| 9 | Exit |

After each option completes, the program pauses and asks you to press Enter before
redrawing the menu  giving  time to read the output before it scrolls away.


## Output tags

Every line of output is prefixed with a colour-coded tag so it is immediately
clear what the program is doing:

| Tag | Colour | Meaning |
|-----|--------|---------|
| `[LIVE]` | Cyan | Data fetched fresh from the server right now |
| `[CACHED]` | Yellow | Data served from the in-memory cache (shows time remaining) |
| `[THREADED]` | Green | Hotel and band API calls running simultaneously in parallel |
| `[WARNING]` | Red | Server returned a 5xx error — will retry |
| `[RETRY]` | Red | Retrying a held-slot query that returned 404 (not yet processed) |

---

## What each file does

### `booking.py`
The entry point. Shows a startup banner explaining the system, then automatically
checks your current reservations before displaying the menu.

The menu shows two live pieces of information on every refresh with no extra API calls:
- **Status line** — last-known booking state, e.g. `Best confirmed booking: Slot 14 (hotel + band)`.
- **Cache hint** — seconds remaining before each service's slot cache expires.

After every menu action the program pauses with `Press Enter to return to menu (or 9 to exit)`
so output is never lost before the user has had a chance to read it.

---

### `view_actions.py`
Read-only actions — nothing here modifies a reservation.

**Option 1 — View current reservations**
Fetches held slots from both services in parallel, groups them into confirmed pairs
(same slot on both services) and unmatched stragglers (only on one service),
then updates the status line.

**Option 2 — View first 20 available slots**
Always bypasses the cache and fetches live data from both servers in parallel.
Shows the first 20 free slots on each service and updates the cache as a side effect.

**Option 5 — View first 5 matching slots**
Finds slots that are free on both hotel and band simultaneously and shows the earliest
five. Uses the cache if it is recent enough to save API calls.

All three print elapsed time so the marker can see how long each parallel fetch took.

---

### `booking_actions.py`
Everything that creates a reservation.

**Option 3 — Book a specific slot (submenu)**
Three sub-options:
- *Book hotel only* — shows available hotel slots first, then reserves the one you enter.
  Reminds you that a matching band slot is still needed.
- *Book band only* — same pattern for the band.
- *Book matching* — shows slots free on both services first, then reserves hotel then band.
  If the hotel succeeds but the band fails, the hotel reservation is released automatically
  so nothing is left dangling.

Slot numbers are validated as 1–550 before any API call is made.

**Option 6 — Reserve the earliest matching slot**
The main automated booking strategy:
- Reads current holdings to find the existing best confirmed pair.
- Retries up to `MAX_RETRIES` times if no matching slots are visible right now —
  availability shifts constantly as other clients compete.
- Only books a new slot if it is earlier than the current best.
- Releases the old confirmed pair only *after* the new one is secured — so you
  are never left without at least one confirmed booking.
- Auto-cleans stray single-service reservations on success.
- Prints total elapsed time and attempt count so the marker can verify the
  1-second rate limit is being respected.

---

### `cancel_actions.py`
Everything that removes a reservation.

**Option 4 — Cancel a specific reservation**
Shows current holdings, asks for a slot number, validates that you actually hold it
(tells you clearly if you do not, without making any API call), then asks hotel/band/both.
Asks for `[y/n]` confirmation before any destructive call. Parallel release if cancelling
the same slot on both services.

**Option 7 — Cancel all unnecessary reservations**
Keeps only the earliest confirmed pair and releases everything else. Shows a clear
`Will keep` / `Will drop` summary before asking for `[y/n]` confirmation.
Matched-pair releases run in parallel. Also triggered automatically after option 6,
but available here so markers can run it manually at any time.

---

### `colours.py`
Single source of truth for all ANSI colour codes and the pre-formatted output tags
(`TAG_LIVE`, `TAG_CACHED`, `TAG_THREADED`, `TAG_WARNING`, `TAG_RETRY`). Every file
imports from here so the style is consistent throughout. Zero dependencies — safe
to import first without circular import risk.

---

### `clients.py`
Loads `api.ini` and creates the two `ReservationApi` instances (`hotel` and `band`)
that every action file imports. Also exposes `MAX_RETRIES` and `DELAY` as constants.

Overrides `warnings.formatwarning` so server-retry messages from `reservationapi.py`
print as clean red `[WARNING]` tags rather than raw file paths and line numbers.

Uses `inline_comment_prefixes=("##", "#")` when parsing the config so the `##`
comments in `api.ini` are not accidentally included in the key or URL values.

---

### `cache.py`
Stores the last-fetched available-slot list for each service and serves it from
memory for up to 30 seconds, avoiding unnecessary API calls.

Prints `[LIVE]` (cyan) when fetching fresh data or `[CACHED]` (yellow) when serving
from memory, always showing how many seconds remain before the cache expires.

Any operation that is about to make a booking always bypasses the cache
(`force_fresh=True`) to ensure it is working with current data.

---

### `helpers.py`
Utility functions shared across the action files:

- `slot_ids()` — converts raw API response format (`[{"id": "14"}, ...]`) to a
  sorted list of integers.
- `get_held_with_retry(api, service)` — wraps `get_slots_held()` with retry logic
  specifically for `NotProcessedError` (404). The spec notes that requests may not
  be processed in order — a 404 right after a reservation is a legitimate distributed
  systems occurrence, not a bug. Retries up to `MAX_RETRIES` times with a delay,
  printing a red `[RETRY]` tag each time.
- `safe_release()` — cancels a slot, prints clear success or failure, clears the cache.
  Returns `True`/`False` so callers can react to failures.
- `free_up_slot()` — when at the 2-reservation limit, drops the highest-numbered
  unmatched slot to make room. Refuses to drop a slot that is part of a confirmed pair.

---

### `parallel.py`
Single function `run_both(fn_hotel, fn_band)` — submits both callables to a
`ThreadPoolExecutor(max_workers=2)` and returns `(hotel_result, band_result)`.

Safe because each thread only ever calls one service — no concurrent requests to
the same API, satisfying the spec's rate-limiting requirement.

Operations that use threading:
- Fetching held slots from both services (options 1, 4, 6, 7, auto-cleanup)
- Fetching available slots from both services (options 2, 3, 5, inside option 6)
- Releasing the same slot on hotel and band simultaneously (options 4, 7, auto-cleanup)

Without threading, each dual-service operation takes ~2 seconds minimum. With
threading it takes ~1 second.

---

### `status.py`
Stores the last-known reservation state as a plain string, updated by any action
that reads the current holdings. The menu reads it on every redraw with no API calls.

Example states:
- `Best confirmed booking: Slot 14 (hotel + band)`
- `No confirmed match yet  |  Held — hotel: 14, band: 20`
- `No reservations held`

---

### `reservationapi.py` (provided)
Low-level HTTP wrapper. Adds the `Authorization: Bearer` header, retries on 5xx
errors, raises typed exceptions for 4xx errors, and enforces a minimum 1-second
delay between requests.

---

### `exceptions.py` (provided)
Typed exceptions raised by `reservationapi.py`:

| Exception | HTTP code | Meaning |
|-----------|-----------|---------|
| `BadRequestError` | 400 | Malformed request |
| `InvalidTokenError` | 401 | API key missing or wrong |
| `BadSlotError` | 403 | Slot number does not exist (valid range: 1–550) |
| `NotProcessedError` | 404 | Request received but not yet processed |
| `SlotUnavailableError` | 409 | Slot already taken by another client |
| `ReservationLimitError` | 451 | Already holding the maximum of 2 reservations |

---

### `api.ini`
Base URLs and API keys for hotel and band, plus global retry count and delay.
