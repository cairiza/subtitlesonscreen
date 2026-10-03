"""
SubtitlesOnScreen - Desktop overlay subtitles for Ubuntu.
"""

from .parser import SubtitleFile, Cue
from .playback import PlaybackEngine
from .overlay import OverlayWindow
from .controller import ControllerWindow
from .app import SubtitlesApp, main

__version__ = "1.0.0"
__all__ = ["SubtitleFile", "Cue", "PlaybackEngine", "OverlayWindow", "ControllerWindow", "SubtitlesApp", "main"]
