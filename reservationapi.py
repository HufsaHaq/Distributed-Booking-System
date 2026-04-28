#!/usr/bin/env python3
""" Reservation API wrapper

This class implements a simple wrapper around the reservation API. It
provides automatic retries for server-side errors, delays to prevent
server overloading, and produces sensible exceptions for the different
types of client-side error that can be encountered.
"""

# This file contains areas that need to be filled in with your own
# implementation code. They are marked with "Your code goes here".
# Comments are included to provide hints about what you should do.

import requests
import simplejson
import warnings
import time

from requests.exceptions import HTTPError
from exceptions import (
    BadRequestError, InvalidTokenError, BadSlotError, NotProcessedError,
    SlotUnavailableError, ReservationLimitError)


class ReservationApi:
    def __init__(self, base_url: str, token: str, retries: int, delay: float):
        """ Create a new ReservationApi to communicate with a reservation
        server.

        Args:
            base_url: The URL of the reservation API to communicate with.
            token: The user's API token obtained from the control panel.
            retries: The maximum number of attempts to make for each request.
            delay: A delay to apply to each request to prevent server overload.
        """
        self.base_url = base_url
        self.token    = token
        self.retries  = retries

        if delay < 1.0:
            warnings.warn(
                f"The configured delay ({delay}s) is below the server's 1-second "
                "rate limit. Raising it to 1.0s to avoid penalisation."
            )
            self.delay = 1.0
        else:
            self.delay = delay

    def _reason(self, req: requests.Response) -> str:
        """Obtain the reason associated with a response"""
        reason = ''
        try:
            json = req.json()
            reason = json['message']
        except simplejson.errors.JSONDecodeError:
            if isinstance(req.reason, bytes):
                try:
                    reason = req.reason.decode('utf-8')
                except UnicodeDecodeError:
                    reason = req.reason.decode('iso-8859-1')
            else:
                reason = req.reason
        return reason

    def _headers(self) -> dict:
        """Return the Authorization header required by every API request."""
        return {"Authorization": f"Bearer {self.token}"}

    def _send_request(self, method: str, endpoint: str) -> dict:
        """
        Send an HTTP request to the API and return the parsed JSON body.

        Retries up to self.retries times when the server returns a 5xx error,
        waiting self.delay seconds between each attempt. Client-side errors
        (4xx) are raised immediately without retrying, since retrying would
        not change the outcome.

        Args:
            method:   HTTP verb: 'GET', 'POST', or 'DELETE'.
            endpoint: Path appended to base_url, e.g. '/reservation/available'.

        Returns:
            Parsed JSON response as a Python dict or list.

        Raises:
            BadRequestError:       400 - the request was malformed.
            InvalidTokenError:     401 - API key is missing or incorrect.
            BadSlotError:          403 - the requested slot does not exist.
            NotProcessedError:     404 - the request has not been processed yet.
            SlotUnavailableError:  409 - someone else already holds this slot.
            ReservationLimitError: 451 - you already hold the maximum of 2 reservations.
            HTTPError:             Any other unexpected status code.
            ConnectionError:       All retry attempts exhausted on server errors.
        """
        url = f"{self.base_url}{endpoint}"

        client_error_map = {
            400: BadRequestError,
            401: InvalidTokenError,
            403: BadSlotError,
            404: NotProcessedError,
            409: SlotUnavailableError,
            451: ReservationLimitError,
        }

        for attempt in range(1, self.retries + 1):
            response = requests.request(method, url, headers=self._headers())

            # Exponential backoff: wait longer on each successive retry to reduce
            # server load. Attempt 1 → base delay, attempt 2 → 2×, attempt 3 → 4×.
            # Always at least self.delay to satisfy the 1-second rate limit.
            backoff = self.delay * (2 ** (attempt - 1))
            if attempt == 1:
                warnings.warn(
                    f"Rate limiting: waiting {backoff:.0f}s before next request "
                    f"(1 request/second minimum required)."
                )
            time.sleep(backoff)

            if response.status_code == 200:
                return response.json()

            if response.status_code >= 500:
                warnings.warn(
                    f"Attempt {attempt}/{self.retries}: server returned "
                    f"{response.status_code} ({self._reason(response)}). "
                    f"Retrying in {self.delay * (2 ** attempt):.0f}s..."
                )
                continue

            # 4xx means the client did something wrong - retrying won't help.
            reason = self._reason(response)
            exc_class = client_error_map.get(response.status_code, HTTPError)
            raise exc_class(reason)

        raise ConnectionError(
            f"Request to {endpoint} failed after {self.retries} attempts. "
            "The server may be temporarily unavailable."
        )

    def get_slots_available(self):
        """Return all slots currently open for reservation on this service."""
        return self._send_request("GET", "/reservation/available")

    def get_slots_held(self):
        """Return all slots you currently hold on this service."""
        return self._send_request("GET", "/reservation")

    def release_slot(self, slot_id):
        """Cancel your existing reservation for the given slot."""
        return self._send_request("DELETE", f"/reservation/{slot_id}")

    def reserve_slot(self, slot_id):
        """
        Attempt to reserve the given slot.

        Raises SlotUnavailableError if another client has already taken it,
        or ReservationLimitError if you already hold 2 reservations.
        """
        return self._send_request("POST", f"/reservation/{slot_id}")