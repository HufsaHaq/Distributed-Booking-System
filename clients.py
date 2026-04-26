#!/usr/bin/env python3
"""
Loads api.ini and creates the two ReservationApi instances used across
the application. Everything that needs `hotel` or `band` imports from here.

Also overrides warnings.formatwarning so server-retry messages from
reservationapi.py print as clean [WARNING] tags rather than raw file paths.
"""

import configparser
import warnings
import reservationapi
from colours import TAG_WARNING

# By default warnings.warn() prints the full file path and line number, which
# looks  bad
# This replaces that with a clean [WARNING] tag t
warnings.formatwarning = lambda msg, *args, **kwargs: f"  {TAG_WARNING} {msg}\n"

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

MAX_RETRIES = int(config['global']['retries'])
DELAY       = max(float(config['global']['delay']), 1.0)