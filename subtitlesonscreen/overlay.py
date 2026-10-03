"""
Floating transparent overlay window for SubtitlesOnScreen.
Displays subtitles always-on-top over all desktop windows in Ubuntu.
Supports:
- True X11 Click-Through mode (mouse passes completely through to apps behind)
- Edit/Drag mode with interactive moving, resizing, and wheel font adjustment
- Customizable font, text outline, background box, and opacity
- Rich text (bold, italic, colors from SRT/VTT)
"""

from typing import Optional
from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect, QApplication
)
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QBrush, QPen, QPainterPath,
    QCursor, QMouseEvent, QWheelEvent
)

from .config import Config
from .parser import Cue
from .x11_utils import set_click_through, IS_X11


class OverlayWindow(QWidget):
    # Signals to communicate with Controller
    sig_lock_toggled = pyqtSignal(bool)       # is_locked
    sig_font_size_changed = pyqtSignal(int)   # new_font_size
    sig_position_changed = pyqtSignal(int, int, int, int) # x, y, w, h
    sig_request_panel = pyqtSignal()

    # Resize edge thresholds
    EDGE_MARGIN = 12

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.is_locked: bool = False  # True = Click-Through enabled, False = Move/Edit mode
        self.current_cue: Optional[Cue] = None

        # Dragging / Resizing state
        self._dragging = False
        self._resizing = False
        self._resize_edges = 0  # Bitmask: 1=Left, 2=Right, 4=Top, 8=Bottom
        self._drag_start_pos = QPoint()
        self._window_start_rect = QRect()

        self._init_window()
        self._init_ui()
        self.apply_config()

    def _init_window(self):
        # Frameless, Always on Top, Tool window (avoids stealing taskbar focus)
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)

        # Translucent background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)

        # Restore geometry from config
        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        w = self.config.get("overlay_width", 900)
        h = self.config.get("overlay_height", 130)
        x = self.config.get("overlay_x", -1)
        y = self.config.get("overlay_y", -1)

        if x < 0 or y < 0:
            # Default to bottom center
            x = (screen_geo.width() - w) // 2
            y = screen_geo.height() - h - 70

        self.setGeometry(x, y, w, h)
        self.setMinimumSize(320, 70)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 12)
        layout.setSpacing(4)

        # Top Control Bar (Only shown in Edit/Unlocked mode on hover)
        self.top_bar = QWidget(self)
        self.top_bar.setObjectName("top_bar")
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(6, 2, 6, 2)
        top_layout.setSpacing(6)

        # Mode hint label
        self.hint_label = QLabel("✥ Arrastra para mover | ⤡ Esquinas para redimensionar | Rueda: Tamaño fuente", self.top_bar)
        self.hint_label.setStyleSheet("color: #a6adc8; font-size: 11px; font-weight: bold; background: transparent;")

        # Lock button
        self.btn_lock = QPushButton("🔒 Bloquear (Click-Through)", self.top_bar)
        self.btn_lock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lock.setStyleSheet("""
            QPushButton {
                background: #e95420;
                color: #ffffff;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background: #ff6e3a;
            }
        """)
        self.btn_lock.clicked.connect(lambda: self.set_locked(True))

        # Open panel button
        self.btn_panel = QPushButton("⚙ Panel", self.top_bar)
        self.btn_panel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_panel.setStyleSheet("""
            QPushButton {
                background: #45475a;
                color: #cdd6f4;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background: #585b70;
            }
        """)
        self.btn_panel.clicked.connect(self.sig_request_panel.emit)

        top_layout.addWidget(self.hint_label)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_panel)
        top_layout.addWidget(self.btn_lock)

        # Subtitle Text Label
        self.sub_label = QLabel(self)
        self.sub_label.setTextFormat(Qt.TextFormat.RichText)
        self.sub_label.setWordWrap(True)
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Drop shadow effect for text outline/shadow
        self.shadow_effect = QGraphicsDropShadowEffect(self)
        self.shadow_effect.setBlurRadius(8)
        self.shadow_effect.setColor(QColor(0, 0, 0, 220))
        self.shadow_effect.setOffset(2, 2)
        self.sub_label.setGraphicsEffect(self.shadow_effect)

        layout.addWidget(self.top_bar)
        layout.addWidget(self.sub_label, 1)

        # Initial placeholder text
        self.set_placeholder()

    def set_placeholder(self):
        """Shows informative preview text when no subtitle file is actively playing."""
        if not self.current_cue:
            self.sub_label.setText(
                "<span style='opacity: 0.8;'><b>SubtitlesOnScreen</b><br/>"
                "<span style='font-size: 0.75em;'>Carga un archivo de subtítulos para comenzar</span></span>"
            )

    def set_cue(self, cue: Optional[Cue]):
        """Updates the rendered subtitle text."""
        self.current_cue = cue
        if cue:
            # Render HTML text (preserves tags like <b>, <i>, etc.)
            self.sub_label.setText(cue.html_text)
        else:
            if self.is_locked:
                # When locked and no dialogue, clear completely for invisible overlay
                self.sub_label.setText("")
            else:
                self.set_placeholder()

    def apply_config(self):
        """Applies font, color, alignment, and background styling from Config."""
        font_family = self.config.get("font_family", "Ubuntu")
        font_size = self.config.get("font_size", 28)
        font_bold = self.config.get("font_bold", True)
        font_italic = self.config.get("font_italic", False)

        font = QFont(font_family, font_size)
        font.setBold(font_bold)
        font.setItalic(font_italic)
        self.sub_label.setFont(font)

        # Text color
        text_color = self.config.get("text_color", "#FFFFFF")
        self.sub_label.setStyleSheet(f"color: {text_color}; background: transparent;")

        # Alignment
        align = self.config.get("text_alignment", "center")
        if align == "left":
            self.sub_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        elif align == "right":
            self.sub_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        else:
            self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Shadow / Outline effect
        outline_enabled = self.config.get("outline_enabled", True)
        outline_color = self.config.get("outline_color", "#000000")
        outline_width = self.config.get("outline_width", 3)

        if outline_enabled and outline_width > 0:
            self.shadow_effect.setEnabled(True)
            self.shadow_effect.setBlurRadius(outline_width * 3)
            self.shadow_effect.setColor(QColor(outline_color))
            self.shadow_effect.setOffset(1, 1)
        else:
            self.shadow_effect.setEnabled(False)

        self.update()

    def set_locked(self, locked: bool):
        """
        Toggles between Click-Through mode (locked=True)
        and Move/Edit mode (locked=False).
        """
        if self.is_locked == locked:
            return

        self.is_locked = locked
        if locked:
            self.top_bar.hide()
            if not self.current_cue:
                self.sub_label.setText("")
            # Set true X11 click-through via XFixes
            set_click_through(int(self.winId()), True)
        else:
            self.top_bar.show()
            if not self.current_cue:
                self.set_placeholder()
            # Restore X11 mouse input
            set_click_through(int(self.winId()), False)

        self.sig_lock_toggled.emit(locked)
        self.update()

    def set_position_preset(self, preset: str):
        """Moves overlay to a standard preset position."""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        w = self.width()
        h = self.height()

        if preset == "bottom_center":
            x = (geo.width() - w) // 2
            y = geo.height() - h - 50
        elif preset == "top_center":
            x = (geo.width() - w) // 2
            y = 50
        elif preset == "center":
            x = (geo.width() - w) // 2
            y = (geo.height() - h) // 2
        else:
            return

        self.move(x, y)
        self.config.set("overlay_x", x)
        self.config.set("overlay_y", y)
        self.config.set("position_preset", preset)
        self.sig_position_changed.emit(x, y, w, h)

    def paintEvent(self, event):
        """Custom background painting for rounded box or banner with configurable opacity."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_style = self.config.get("background_style", "rounded_box")
        bg_color_hex = self.config.get("background_color", "#11111b")
        bg_opacity = self.config.get("background_opacity", 0.65)
        border_radius = self.config.get("border_radius", 12)

        # In edit mode or when text is present, draw background if opacity > 0
        should_draw_bg = (not self.is_locked) or (self.current_cue is not None)

        if should_draw_bg and bg_style != "none" and bg_opacity > 0.01:
            color = QColor(bg_color_hex)
            color.setAlphaF(bg_opacity)

            rect = self.rect().adjusted(2, 2, -2, -2)
            path = QPainterPath()

            if bg_style == "banner":
                path.addRect(self.rect())
            else:
                path.addRoundedRect(rect.toRectF(), border_radius, border_radius)

            painter.fillPath(path, QBrush(color))

        # In Edit mode (unlocked), draw an accent dashed border indicating interactive bounding box
        if not self.is_locked:
            pen = QPen(QColor(233, 84, 32, 180), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -3, -3), border_radius, border_radius)

        painter.end()

    # --- Mouse Interaction for Moving & Resizing (Active only when NOT locked) ---

    def _determine_edges(self, pos: QPoint) -> int:
        """Determines if mouse is near any edge for resizing."""
        edges = 0
        m = self.EDGE_MARGIN
        w = self.width()
        h = self.height()

        if pos.x() <= m:
            edges |= 1  # Left
        elif pos.x() >= w - m:
            edges |= 2  # Right

        if pos.y() <= m:
            edges |= 4  # Top
        elif pos.y() >= h - m:
            edges |= 8  # Bottom

        return edges

    def _update_cursor_for_edges(self, edges: int):
        if self.is_locked:
            self.unsetCursor()
            return

        if edges in (1 | 4, 2 | 8):  # Top-left or Bottom-right
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges in (2 | 4, 1 | 8):  # Top-right or Bottom-left
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges in (1, 2):  # Left or Right
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges in (4, 8):  # Top or Bottom
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event: QMouseEvent):
        if self.is_locked:
            return super().mousePressEvent(event)

        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._determine_edges(event.pos())
            self._drag_start_pos = event.globalPosition().toPoint()
            self._window_start_rect = self.geometry()

            if edges != 0:
                self._resizing = True
                self._resize_edges = edges
            else:
                self._dragging = True

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_locked:
            return super().mouseMoveEvent(event)

        if not self._dragging and not self._resizing:
            edges = self._determine_edges(event.pos())
            self._update_cursor_for_edges(edges)
            return

        delta = event.globalPosition().toPoint() - self._drag_start_pos
        r = QRect(self._window_start_rect)

        if self._dragging:
            self.move(r.topLeft() + delta)
            self._save_geometry()
        elif self._resizing:
            if self._resize_edges & 1:  # Left
                r.setLeft(min(r.left() + delta.x(), r.right() - self.minimumWidth()))
            elif self._resize_edges & 2:  # Right
                r.setRight(max(r.right() + delta.x(), r.left() + self.minimumWidth()))

            if self._resize_edges & 4:  # Top
                r.setTop(min(r.top() + delta.y(), r.bottom() - self.minimumHeight()))
            elif self._resize_edges & 8:  # Bottom
                r.setBottom(max(r.bottom() + delta.y(), r.top() + self.minimumHeight()))

            self.setGeometry(r)
            self._save_geometry()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.is_locked:
            return super().mouseReleaseEvent(event)

        self._dragging = False
        self._resizing = False
        self._save_geometry()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Double clicking in edit mode locks into click-through mode."""
        if not self.is_locked:
            self.set_locked(True)

    def wheelEvent(self, event: QWheelEvent):
        """Scrolling the mouse wheel adjusts the font size dynamically."""
        if self.is_locked:
            return

        num_degrees = event.angleDelta().y() / 8
        num_steps = int(num_degrees / 15)
        if num_steps != 0:
            cur_size = self.config.get("font_size", 28)
            new_size = max(14, min(72, cur_size + (2 if num_steps > 0 else -2)))
            if new_size != cur_size:
                self.config.set("font_size", new_size)
                self.apply_config()
                self.sig_font_size_changed.emit(new_size)

    def _save_geometry(self):
        """Saves current window coordinates to config."""
        self.config.set("overlay_x", self.x(), auto_save=False)
        self.config.set("overlay_y", self.y(), auto_save=False)
        self.config.set("overlay_width", self.width(), auto_save=False)
        self.config.set("overlay_height", self.height(), auto_save=True)
        self.sig_position_changed.emit(self.x(), self.y(), self.width(), self.height())
