"""
Subtitle parser module supporting SRT, VTT, and related subtitle formats.
Handles multiple encodings, varied timecode formats, HTML formatting tags,
and provides efficient binary-search cue lookup.
"""

from dataclasses import dataclass
import os
import re
from typing import List, Optional, Tuple
import bisect


@dataclass
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str
    html_text: str

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def is_active(self, current_ms: int) -> bool:
        return self.start_ms <= current_ms <= self.end_ms


def format_ms_to_timestamp(ms: int, show_millis: bool = True) -> str:
    """Format milliseconds into HH:MM:SS or HH:MM:SS,mmm"""
    if ms < 0:
        ms = 0
    total_seconds = ms // 1000
    millis = ms % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if show_millis:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
    else:
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"


def parse_timestamp_to_ms(ts: str) -> Optional[int]:
    """
    Parse a timestamp string into milliseconds.
    Supports formats:
    - 00:01:23,456 or 00:01:23.456
    - 01:23.456
    - 0:01:23.456
    """
    ts = ts.strip().replace(",", ".")
    # Match HH:MM:SS.mmm
    match = re.match(r"^(\d+):(\d{2}):(\d{2})(?:\.(\d+))?$", ts)
    if match:
        h, m, s, frac = match.groups()
        ms = int(h) * 3600_000 + int(m) * 60_000 + int(s) * 1000
        if frac:
            # Pad or truncate frac to 3 digits (milliseconds)
            frac = frac[:3].ljust(3, "0")
            ms += int(frac)
        return ms

    # Match MM:SS.mmm
    match = re.match(r"^(\d{1,2}):(\d{2})(?:\.(\d+))?$", ts)
    if match:
        m, s, frac = match.groups()
        ms = int(m) * 60_000 + int(s) * 1000
        if frac:
            frac = frac[:3].ljust(3, "0")
            ms += int(frac)
        return ms

    return None


def clean_text(raw_text: str) -> Tuple[str, str]:
    """
    Cleans raw subtitle text:
    - Strips SSA/ASS tags like {\\an8}, {\\pos(x,y)}, etc.
    - Strips or preserves valid HTML tags (<b>, <i>, <u>, <font>).
    Returns (plain_text, html_text).
    """
    # Remove ASS/SSA style curly brace codes: { ... }
    text = re.sub(r"\{.*?\}", "", raw_text)
    text = text.strip()

    # Plain text version: strip all HTML tags
    plain = re.sub(r"<[^>]+>", "", text).strip()

    # HTML text version: convert newlines to <br/>
    # and preserve basic tags: <b>, <i>, <u>, <font>
    html = text.replace("\r\n", "\n").replace("\r", "\n")
    # Escape any rogue ampersands not part of an entity
    html = re.sub(r"&(?!amp;|lt;|gt;|quot;|#\d+;)", "&amp;", html)
    html = html.replace("\n", "<br/>")

    return plain, html


class SubtitleFile:
    def __init__(self, filepath: str = "", cues: Optional[List[Cue]] = None):
        self.filepath: str = filepath
        self.filename: str = os.path.basename(filepath) if filepath else ""
        self.cues: List[Cue] = cues or []
        self._start_times: List[int] = [c.start_ms for c in self.cues]
        self.duration_ms: int = max((c.end_ms for c in self.cues), default=0)

    @classmethod
    def load(cls, filepath: str) -> "SubtitleFile":
        """Loads and parses a subtitle file from disk with robust encoding detection."""
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Subtitle file not found: {filepath}")

        raw_bytes = None
        with open(filepath, "rb") as f:
            raw_bytes = f.read()

        # Try encodings in priority order
        encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-15"]
        content = ""
        for enc in encodings:
            try:
                content = raw_bytes.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if not content:
            content = raw_bytes.decode("utf-8", errors="replace")

        cues = cls.parse_content(content)
        return cls(filepath=filepath, cues=cues)

    @classmethod
    def parse_content(cls, content: str) -> List[Cue]:
        """Parses subtitle content string (SRT or VTT)."""
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        # Strip WebVTT headers
        if content.startswith("WEBVTT"):
            # Skip until after the first blank line or header block
            lines = content.split("\n")
            start_idx = 0
            for i, line in enumerate(lines):
                if line.strip() == "":
                    start_idx = i + 1
                    break
            content = "\n".join(lines[start_idx:])

        # Split into blocks separated by two or more newlines
        blocks = re.split(r"\n\s*\n+", content.strip())
        cues: List[Cue] = []
        cue_idx = 1

        for block in blocks:
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            if not lines:
                continue

            # Look for timestamp line: contains "-->"
            ts_line_idx = -1
            for i, line in enumerate(lines):
                if "-->" in line:
                    ts_line_idx = i
                    break

            if ts_line_idx == -1:
                continue

            ts_line = lines[ts_line_idx]
            parts = ts_line.split("-->")
            if len(parts) < 2:
                continue

            # Start time and end time (strip optional VTT positioning settings like align:start)
            start_str = parts[0].strip()
            end_part = parts[1].strip()
            # In VTT, end time may be followed by positioning settings: "00:02.000 line:0%"
            end_tokens = end_part.split()
            end_str = end_tokens[0] if end_tokens else end_part

            start_ms = parse_timestamp_to_ms(start_str)
            end_ms = parse_timestamp_to_ms(end_str)

            if start_ms is None or end_ms is None:
                continue

            if end_ms < start_ms:
                # Malformed end time; give it a default 2s duration
                end_ms = start_ms + 2000

            text_lines = lines[ts_line_idx + 1:]
            raw_text = "\n".join(text_lines).strip()
            if not raw_text:
                continue

            plain_text, html_text = clean_text(raw_text)

            cues.append(Cue(
                index=cue_idx,
                start_ms=start_ms,
                end_ms=end_ms,
                text=plain_text,
                html_text=html_text
            ))
            cue_idx += 1

        # Sort cues strictly by start time
        cues.sort(key=lambda c: (c.start_ms, c.end_ms))
        # Re-index
        for i, c in enumerate(cues, 1):
            c.index = i

        return cues

    def find_cue_at(self, time_ms: int) -> Optional[Cue]:
        """
        Returns the active cue at `time_ms`, or None if no cue is active.
        Uses binary search for O(log N) lookup.
        """
        if not self.cues:
            return None

        # Binary search for cue where start_ms <= time_ms
        idx = bisect.bisect_right(self._start_times, time_ms) - 1
        if idx >= 0:
            cue = self.cues[idx]
            if cue.start_ms <= time_ms <= cue.end_ms:
                return cue
            # Also check previous cues in case of overlapping cues
            for i in range(idx - 1, max(-1, idx - 4), -1):
                prev_cue = self.cues[i]
                if prev_cue.start_ms <= time_ms <= prev_cue.end_ms:
                    return prev_cue

        # Also check idx + 1 if within range
        if 0 <= idx + 1 < len(self.cues):
            next_cue = self.cues[idx + 1]
            if next_cue.start_ms <= time_ms <= next_cue.end_ms:
                return next_cue

        return None

    def find_cue_index(self, time_ms: int) -> int:
        """Finds index in cues list closest to or active at time_ms, or -1."""
        cue = self.find_cue_at(time_ms)
        if cue:
            return cue.index - 1

        # If not active, find the next upcoming cue
        idx = bisect.bisect_right(self._start_times, time_ms)
        if 0 <= idx < len(self.cues):
            return idx
        elif self.cues:
            return len(self.cues) - 1
        return -1

    def search(self, query: str) -> List[Cue]:
        """Searches cues for query text (case-insensitive)."""
        if not query:
            return self.cues
        q = query.lower()
        return [c for c in self.cues if q in c.text.lower()]
