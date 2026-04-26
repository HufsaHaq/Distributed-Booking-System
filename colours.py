#!/usr/bin/env python3
"""
ANSI colour codes and pre-formatted output tag strings used across the
application. Centralised here so every file uses the same style.

Tags are printed before operations to make it immediately clear what kind of action the program is taking.
"""

# Base codes
PINK   = "\033[35m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
WHITE  = "\033[37m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

TAG_LIVE     = CYAN   + "[LIVE]    " + RESET  # fresh server fetch
TAG_CACHED   = YELLOW + "[CACHED]  " + RESET  # served from in-memory cache
TAG_THREADED = GREEN  + "[THREADED]" + RESET  # parallel hotel + band call
TAG_WARNING  = RED    + "[WARNING] " + RESET  # server error / retry
TAG_RETRY    = RED    + "[RETRY]   " + RESET  # explicit retry attempt