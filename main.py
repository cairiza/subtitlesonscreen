#!/usr/bin/env python3
"""
SubtitlesOnScreen - Main entry point.
Run directly with:
    python3 main.py
or
    python3 main.py /path/to/movie.srt
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from subtitlesonscreen.app import main

if __name__ == "__main__":
    main()
