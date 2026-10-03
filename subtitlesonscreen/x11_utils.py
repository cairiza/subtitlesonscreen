"""
X11 utilities for SubtitlesOnScreen.
- Implements Click-Through (input transparency) using XFixes extension.
- Implements Global Desktop Shortcuts using XGrabKey so users can control
  subtitles even when another window (VLC, Chrome, game) is in focus.
"""

import ctypes
import os
import time
import threading
from typing import Dict, Optional
from PyQt6.QtCore import QObject, pyqtSignal

# Check if running under X11
IS_X11 = os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11" or (
    "DISPLAY" in os.environ and not os.environ.get("WAYLAND_DISPLAY")
)

# Load X11 libraries and define exact ctypes signatures for 64-bit stability
try:
    _x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
    _x11.XOpenDisplay.restype = ctypes.c_void_p
    _x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    _x11.XCloseDisplay.restype = ctypes.c_int
    _x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    _x11.XFlush.restype = ctypes.c_int
    _x11.XFlush.argtypes = [ctypes.c_void_p]
    _x11.XDefaultRootWindow.restype = ctypes.c_ulong
    _x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    _x11.XKeysymToKeycode.restype = ctypes.c_ubyte
    _x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    _x11.XGrabKey.restype = ctypes.c_int
    _x11.XGrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _x11.XPending.restype = ctypes.c_int
    _x11.XPending.argtypes = [ctypes.c_void_p]
    _x11.XNextEvent.restype = ctypes.c_int
    _x11.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
except Exception:
    _x11 = None

try:
    _xfixes = ctypes.cdll.LoadLibrary("libXfixes.so.3")
    _xfixes.XFixesSetWindowShapeRegion.restype = None
    _xfixes.XFixesSetWindowShapeRegion.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_void_p
    ]
except Exception:
    _xfixes = None

try:
    _xshape = ctypes.cdll.LoadLibrary("libXext.so.6")
    _xshape.XShapeCombineMask.restype = None
    _xshape.XShapeCombineMask.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int
    ]
except Exception:
    _xshape = None

# X11 Constants
ShapeBounding = 0
ShapeClip = 1
ShapeInput = 2
ShapeSet = 0

ShiftMask = 1 << 0
LockMask = 1 << 1
ControlMask = 1 << 2
Mod1Mask = 1 << 3  # Alt
Mod2Mask = 1 << 4  # NumLock
Mod4Mask = 1 << 6  # Super / Windows key

KeyPress = 2
KeyRelease = 3


class XKeyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("root", ctypes.c_ulong),
        ("subwindow", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x_root", ctypes.c_int),
        ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("keycode", ctypes.c_uint),
        ("same_screen", ctypes.c_int),
    ]


def set_click_through(win_id: int, enable: bool) -> bool:
    """
    Sets whether the specified X11 window allows mouse events to pass straight through
    to windows underneath it.
    """
    if not (_x11 and _xfixes and _xshape):
        return False

    display = _x11.XOpenDisplay(None)
    if not display:
        return False

    try:
        if enable:
            # Empty input region: all mouse clicks pass straight through!
            _xfixes.XFixesSetWindowShapeRegion(display, win_id, ShapeInput, 0, 0, None)
        else:
            # Restore normal input shape
            _xshape.XShapeCombineMask(display, win_id, ShapeInput, 0, 0, None, ShapeSet)

        _x11.XFlush(display)
        return True
    except Exception as e:
        print(f"[X11] Error setting click through: {e}")
        return False
    finally:
        _x11.XCloseDisplay(display)


class X11GlobalHotkeys(QObject):
    """
    Background worker that listens for global X11 hotkeys across the entire desktop.
    Default hotkeys:
      Alt + Shift + P: Play / Pause
      Alt + Shift + L: Toggle Lock / Click-Through
      Alt + Shift + Left: Rewind 5s
      Alt + Shift + Right: Forward 5s
      Alt + Shift + Up: Previous Cue
      Alt + Shift + Down: Next Cue
      Alt + Shift + [: Sync Delay -100ms
      Alt + Shift + ]: Sync Delay +100ms
    """
    sig_play_pause = pyqtSignal()
    sig_toggle_lock = pyqtSignal()
    sig_seek_backward = pyqtSignal()
    sig_seek_forward = pyqtSignal()
    sig_prev_cue = pyqtSignal()
    sig_next_cue = pyqtSignal()
    sig_offset_minus = pyqtSignal()
    sig_offset_plus = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if not _x11:
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None

    def _run_loop(self):
        display = None
        try:
            display = _x11.XOpenDisplay(None)
            if not display:
                return
            root = _x11.XDefaultRootWindow(display)

            # Modifier mask combinations to ignore NumLock and CapsLock
            mod_variants = [
                Mod1Mask | ShiftMask,
                Mod1Mask | ShiftMask | Mod2Mask,
                Mod1Mask | ShiftMask | LockMask,
                Mod1Mask | ShiftMask | Mod2Mask | LockMask,
            ]

            # Keysym mappings
            actions_by_keysym = {
                0x0070: self.sig_play_pause,      # 'p'
                0x0050: self.sig_play_pause,      # 'P'
                0x006c: self.sig_toggle_lock,     # 'l'
                0x004c: self.sig_toggle_lock,     # 'L'
                0xff51: self.sig_seek_backward,   # Left arrow
                0xff53: self.sig_seek_forward,    # Right arrow
                0xff52: self.sig_prev_cue,        # Up arrow
                0xff54: self.sig_next_cue,        # Down arrow
                0x005b: self.sig_offset_minus,    # '['
                0x005d: self.sig_offset_plus,     # ']'
            }

            keycodes_to_action: Dict[int, pyqtSignal] = {}

            # Grab keys
            for keysym, sig in actions_by_keysym.items():
                keycode = _x11.XKeysymToKeycode(display, keysym)
                if keycode > 0:
                    keycodes_to_action[keycode] = sig
                    for mod in mod_variants:
                        _x11.XGrabKey(display, keycode, mod, root, True, 1, 1)

            _x11.XFlush(display)

            # Event structure buffer
            event_buf = (ctypes.c_byte * 256)()

            while self._running:
                # Non-blocking check with XPending
                pending = _x11.XPending(display)
                if pending > 0:
                    _x11.XNextEvent(display, ctypes.byref(event_buf))
                    event_type = ctypes.cast(ctypes.byref(event_buf), ctypes.POINTER(ctypes.c_int)).contents.value
                    if event_type == KeyPress:
                        key_event = ctypes.cast(ctypes.byref(event_buf), ctypes.POINTER(XKeyEvent)).contents
                        kc = key_event.keycode
                        if kc in keycodes_to_action:
                            keycodes_to_action[kc].emit()
                else:
                    time.sleep(0.04)

        except Exception as e:
            pass
        finally:
            if display and _x11:
                try:
                    _x11.XCloseDisplay(display)
                except Exception:
                    pass
