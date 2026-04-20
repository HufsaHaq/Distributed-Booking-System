#!/usr/bin/env python3
"""
clients

Loads api.ini and creates the two ReservationApi instances used across
the application. Everything that needs `hotel` or `band` imports from here.
"""

import configparser
import warnings
import reservationapi

# By default warnings.warn() prints the full file path and line number, which
# looks  bad
# This replaces that with a clean [WARNING] tag t
warnings.formatwarning = lambda msg, *args, **kwargs: f"  [WARNING] {msg}\n"

config = configparser.ConfigParser(inline_comment_prefixes=("##", "#"))
config.read("api.ini")

hotel = reservationapi.ReservationApi(
    config['hotel']['url'],
    config['hotel']['key'],
    int(config['global']['retries']),
    float(config['global']['delay']),
)

band = reservationapi.ReservationApi(
    config['band']['url'],
    config['band']['key'],
    int(config['global']['retries']),
    float(config['global']['delay']),
)

# Expose these so other modules don't need to re-parse the config.
MAX_RETRIES = int(config['global']['retries'])
DELAY       = max(float(config['global']['delay']), 1.0)
