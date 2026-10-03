"""
Configuration manager for SubtitlesOnScreen.
Persists application settings in ~/.config/subtitlesonscreen/settings.json.
"""

import json
import os
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    # Overlay Geometry & Position
    "overlay_x": -1,  # -1 means auto-center horizontally
    "overlay_y": -1,  # -1 means auto-place at bottom
    "overlay_width": 900,
    "overlay_height": 130,
    "position_preset": "bottom_center",  # "bottom_center", "top_center", "center", "custom"

    # Overlay Typography & Appearance
    "font_family": "Ubuntu",
    "font_size": 28,
    "font_bold": True,
    "font_italic": False,
    "text_color": "#FFFFFF",
    "outline_enabled": True,
    "outline_color": "#000000",
    "outline_width": 3,
    "background_style": "rounded_box",  # "rounded_box", "banner", "none"
    "background_color": "#11111b",
    "background_opacity": 0.65,
    "text_alignment": "center",  # "center", "left", "right"
    "border_radius": 12,
    "padding_h": 24,
    "padding_v": 12,

    # Controller Window
    "controller_x": -1,
    "controller_y": -1,
    "controller_width": 780,
    "controller_height": 560,
    "controller_always_on_top": False,

    # Playback Settings
    "last_file": "",
    "last_time_ms": 0,
    "sync_offset_ms": 0,
    "playback_speed": 1.0,
    "click_through": False,
    "global_hotkeys_enabled": True,
}


class Config:
    def __init__(self):
        config_dir = os.path.expanduser("~/.config/subtitlesonscreen")
        os.makedirs(config_dir, exist_ok=True)
        self.config_file = os.path.join(config_dir, "settings.json")
        self.data: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if os.path.isfile(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        self.data.update(saved)
            except Exception as e:
                print(f"[Config] Error loading settings: {e}")

    def save(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Error saving settings: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any, auto_save: bool = True):
        self.data[key] = value
        if auto_save:
            self.save()

    def update(self, mapping: Dict[str, Any], auto_save: bool = True):
        self.data.update(mapping)
        if auto_save:
            self.save()
