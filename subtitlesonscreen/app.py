"""
Application orchestrator and entry point for SubtitlesOnScreen.
Coordinates the overlay window, controller window, playback engine,
system tray icon, and global hotkeys.
"""

import sys
import os
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction

from .config import Config
from .parser import Cue
from .playback import PlaybackEngine
from .overlay import OverlayWindow
from .controller import ControllerWindow
from .x11_utils import X11GlobalHotkeys, IS_X11


class SubtitlesApp:
    def __init__(self, subtitle_path: Optional[str] = None):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("SubtitlesOnScreen")
        self.app.setApplicationDisplayName("Subtitles on Screen")
        self.app.setQuitOnLastWindowClosed(False)

        # Assets
        self.assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
        self.icon_path = os.path.join(self.assets_dir, "icon.png")
        if os.path.isfile(self.icon_path):
            self.app_icon = QIcon(self.icon_path)
            self.app.setWindowIcon(self.app_icon)
        else:
            self.app_icon = QIcon()

        # Core Components
        self.config = Config()
        self.engine = PlaybackEngine()
        self.overlay = OverlayWindow(self.config)
        self.controller = ControllerWindow(self.config, self.engine, self.overlay)

        # Global Desktop Hotkeys (X11)
        self.hotkeys: Optional[X11GlobalHotkeys] = None
        if IS_X11 and self.config.get("global_hotkeys_enabled", True):
            self._setup_global_hotkeys()

        # System Tray
        self._setup_tray_icon()

        # Load file passed via command line if any
        if subtitle_path and os.path.isfile(subtitle_path):
            self.controller.load_subtitle_file(subtitle_path)

        # Connect cleanup
        self.app.aboutToQuit.connect(self._on_cleanup)

    def _setup_global_hotkeys(self):
        self.hotkeys = X11GlobalHotkeys(self.overlay)
        self.hotkeys.sig_play_pause.connect(self.engine.toggle_play)
        self.hotkeys.sig_toggle_lock.connect(self._toggle_lock)
        self.hotkeys.sig_seek_backward.connect(lambda: self.engine.seek_relative(-5000))
        self.hotkeys.sig_seek_forward.connect(lambda: self.engine.seek_relative(5000))
        self.hotkeys.sig_prev_cue.connect(self.engine.previous_cue)
        self.hotkeys.sig_next_cue.connect(self.engine.next_cue)
        self.hotkeys.sig_offset_minus.connect(lambda: self.engine.add_offset(-100))
        self.hotkeys.sig_offset_plus.connect(lambda: self.engine.add_offset(100))
        self.hotkeys.start()

    def _setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(self.app_icon, self.overlay)
        tray_menu = QMenu()

        self.act_play = QAction("▶ Reproducir", tray_menu)
        self.act_play.triggered.connect(self.engine.toggle_play)

        self.act_lock = QAction("🔒 Modo Click-Through", tray_menu)
        self.act_lock.setCheckable(True)
        self.act_lock.setChecked(self.overlay.is_locked)
        self.act_lock.triggered.connect(self._toggle_lock)

        self.act_toggle_overlay = QAction("👁 Mostrar Subtítulos", tray_menu)
        self.act_toggle_overlay.setCheckable(True)
        self.act_toggle_overlay.setChecked(True)
        self.act_toggle_overlay.triggered.connect(self._toggle_overlay_visibility)

        self.act_panel = QAction("⚙ Abrir Panel de Control", tray_menu)
        self.act_panel.triggered.connect(self.controller.show_and_raise)

        act_quit = QAction("❌ Salir", tray_menu)
        act_quit.triggered.connect(self.quit)

        tray_menu.addAction(self.act_play)
        tray_menu.addSeparator()
        tray_menu.addAction(self.act_lock)
        tray_menu.addAction(self.act_toggle_overlay)
        tray_menu.addSeparator()
        tray_menu.addAction(self.act_panel)
        tray_menu.addSeparator()
        tray_menu.addAction(act_quit)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        # Update tray on state changes
        self.engine.sig_state_changed.connect(
            lambda is_playing: self.act_play.setText("⏸ Pausar" if is_playing else "▶ Reproducir")
        )
        self.overlay.sig_lock_toggled.connect(self.act_lock.setChecked)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.controller.show_and_raise()

    def _toggle_lock(self):
        new_state = not self.overlay.is_locked
        self.overlay.set_locked(new_state)

    def _toggle_overlay_visibility(self, visible: bool):
        if visible:
            self.overlay.show()
        else:
            self.overlay.hide()

    def _on_cleanup(self):
        if self.hotkeys:
            self.hotkeys.stop()
        self.config.save()

    def run(self) -> int:
        # Show both overlay and controller
        self.overlay.show()
        self.controller.show()
        return self.app.exec()

    def quit(self):
        self._on_cleanup()
        self.app.quit()


def main():
    subtitle_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = SubtitlesApp(subtitle_path)
    sys.exit(app.run())
