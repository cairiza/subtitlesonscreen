"""
Accurate playback engine for SubtitlesOnScreen.
Uses QElapsedTimer to ensure zero drift regardless of system load or timer jitter.
Provides seeking, speed scaling, fine sync offset calibration, and cue navigation.
"""

from typing import Optional
from PyQt6.QtCore import QObject, QTimer, QElapsedTimer, pyqtSignal

from .parser import SubtitleFile, Cue, format_ms_to_timestamp


class PlaybackEngine(QObject):
    # Signals
    sig_cue_changed = pyqtSignal(object)  # Optional[Cue]
    sig_time_updated = pyqtSignal(int, int, str)  # current_ms, total_ms, formatted_time_str
    sig_state_changed = pyqtSignal(bool)  # is_playing
    sig_offset_changed = pyqtSignal(int)  # offset_ms
    sig_speed_changed = pyqtSignal(float)  # speed multiplier
    sig_file_loaded = pyqtSignal(str, int, int)  # filepath, cue_count, duration_ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sub_file: Optional[SubtitleFile] = None
        self.is_playing: bool = False

        self._anchor_time_ms: int = 0
        self._offset_ms: int = 0
        self._speed: float = 1.0
        self._elapsed_timer = QElapsedTimer()

        self._current_cue_idx: int = -1
        self._last_emitted_time_ms: int = -1

        # Periodic update timer (runs at 40 FPS / 25ms intervals)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(25)
        self._tick_timer.timeout.connect(self._on_tick)

    @property
    def current_time_ms(self) -> int:
        """Returns the current raw timeline position in milliseconds (without offset)."""
        if not self.is_playing or not self._elapsed_timer.isValid():
            return self._anchor_time_ms

        elapsed = self._elapsed_timer.elapsed()
        calculated = self._anchor_time_ms + int(elapsed * self._speed)
        # Cap at total duration if file loaded
        if self.sub_file and self.sub_file.duration_ms > 0:
            if calculated > self.sub_file.duration_ms + 1000:
                calculated = self.sub_file.duration_ms + 1000
        return max(0, calculated)

    @property
    def effective_time_ms(self) -> int:
        """Returns the timeline position adjusted by the synchronization offset."""
        return max(0, self.current_time_ms + self._offset_ms)

    @property
    def total_duration_ms(self) -> int:
        return self.sub_file.duration_ms if self.sub_file else 0

    @property
    def offset_ms(self) -> int:
        return self._offset_ms

    @property
    def speed(self) -> float:
        return self._speed

    def load_file(self, filepath: str) -> bool:
        """Loads and parses a subtitle file, resetting timeline state."""
        try:
            self.pause()
            sub = SubtitleFile.load(filepath)
            self.sub_file = sub
            self._anchor_time_ms = 0
            self._current_cue_idx = -1
            self._last_emitted_time_ms = -1
            self.sig_file_loaded.emit(filepath, len(sub.cues), sub.duration_ms)
            self._update_current_cue()
            self._emit_time_update(force=True)
            return True
        except Exception as e:
            print(f"[Playback] Failed to load subtitle file {filepath}: {e}")
            return False

    def play(self):
        """Starts or resumes playback."""
        if self.is_playing:
            return
        if not self.sub_file or not self.sub_file.cues:
            return

        # If at or past the end, restart from beginning
        if self.sub_file.duration_ms > 0 and self._anchor_time_ms >= self.sub_file.duration_ms:
            self._anchor_time_ms = 0

        self.is_playing = True
        self._elapsed_timer.restart()
        self._tick_timer.start()
        self.sig_state_changed.emit(True)

    def pause(self):
        """Pauses playback at the current position."""
        if not self.is_playing:
            return

        # Commit elapsed time to anchor
        self._anchor_time_ms = self.current_time_ms
        self._elapsed_timer.invalidate()
        self.is_playing = False
        self._tick_timer.stop()
        self.sig_state_changed.emit(False)
        self._emit_time_update(force=True)

    def toggle_play(self):
        """Toggles between play and pause."""
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def stop(self):
        """Stops playback and rewinds to 0."""
        self.pause()
        self.seek(0)

    def seek(self, target_ms: int):
        """Seeks to an absolute millisecond position."""
        target_ms = max(0, target_ms)
        if self.sub_file and self.sub_file.duration_ms > 0:
            target_ms = min(target_ms, self.sub_file.duration_ms + 1000)

        self._anchor_time_ms = target_ms
        if self.is_playing:
            self._elapsed_timer.restart()

        self._current_cue_idx = -1
        self._update_current_cue()
        self._emit_time_update(force=True)

    def seek_relative(self, delta_ms: int):
        """Seeks relative to current position (e.g. +5000ms or -5000ms)."""
        self.seek(self.current_time_ms + delta_ms)

    def next_cue(self):
        """Jumps directly to the start of the next subtitle."""
        if not self.sub_file or not self.sub_file.cues:
            return

        cur_time = self.effective_time_ms
        for cue in self.sub_file.cues:
            if cue.start_ms > cur_time + 100:
                self.seek(cue.start_ms - self._offset_ms)
                return

    def previous_cue(self):
        """Jumps directly to previous subtitle or start of current one."""
        if not self.sub_file or not self.sub_file.cues:
            return

        cur_time = self.effective_time_ms
        # If currently inside a cue and more than 500ms in, jump to start of current cue
        active_cue = self.sub_file.find_cue_at(cur_time)
        if active_cue and cur_time - active_cue.start_ms > 600:
            self.seek(active_cue.start_ms - self._offset_ms)
            return

        # Otherwise find previous cue
        prev_cue = None
        for cue in self.sub_file.cues:
            if cue.start_ms < cur_time - 100:
                prev_cue = cue
            else:
                break

        if prev_cue:
            self.seek(prev_cue.start_ms - self._offset_ms)
        else:
            self.seek(0)

    def set_speed(self, speed: float):
        """Sets playback speed multiplier (0.25x to 4.0x)."""
        if speed <= 0:
            return
        speed = round(speed, 2)
        if self.is_playing:
            # Commit current time before changing rate
            self._anchor_time_ms = self.current_time_ms
            self._elapsed_timer.restart()

        self._speed = speed
        self.sig_speed_changed.emit(self._speed)

    def set_offset(self, offset_ms: int):
        """Sets sync offset in milliseconds."""
        self._offset_ms = offset_ms
        self.sig_offset_changed.emit(self._offset_ms)
        self._update_current_cue()
        self._emit_time_update(force=True)

    def add_offset(self, delta_ms: int):
        """Adds or subtracts offset (e.g. +100ms or -100ms)."""
        self.set_offset(self._offset_ms + delta_ms)

    def reset_offset(self):
        """Resets sync offset to 0."""
        self.set_offset(0)

    def _on_tick(self):
        """Periodic tick handler."""
        if not self.sub_file:
            return

        # Check if playback reached the end
        if self.sub_file.duration_ms > 0 and self.current_time_ms > self.sub_file.duration_ms + 1500:
            self.pause()
            self.seek(self.sub_file.duration_ms)
            return

        self._update_current_cue()
        self._emit_time_update()

    def _update_current_cue(self):
        """Checks and emits active cue if changed."""
        if not self.sub_file:
            if self._current_cue_idx != -1:
                self._current_cue_idx = -1
                self.sig_cue_changed.emit(None)
            return

        active_cue = self.sub_file.find_cue_at(self.effective_time_ms)
        new_idx = active_cue.index if active_cue else -1

        if new_idx != self._current_cue_idx:
            self._current_cue_idx = new_idx
            self.sig_cue_changed.emit(active_cue)

    def _emit_time_update(self, force: bool = False):
        """Emits time update signal throttled to ~10Hz (every 100ms) unless forced."""
        cur = self.current_time_ms
        if force or abs(cur - self._last_emitted_time_ms) >= 80:
            self._last_emitted_time_ms = cur
            tot = self.total_duration_ms
            cur_str = format_ms_to_timestamp(cur, show_millis=False)
            tot_str = format_ms_to_timestamp(tot, show_millis=False)
            fmt_str = f"{cur_str} / {tot_str}"
            self.sig_time_updated.emit(cur, tot, fmt_str)
