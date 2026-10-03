"""
Control Panel Window for SubtitlesOnScreen.
Provides playback controls, audio sync calibration, appearance customizer,
subtitle explorer with live search, and mode toggles.
"""

import os
from typing import Optional, List
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSlider, QTabWidget, QFileDialog,
    QColorDialog, QFontComboBox, QCheckBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QGroupBox, QFrame, QMessageBox, QApplication
)
from PyQt6.QtGui import QColor, QFont, QIcon, QKeySequence, QShortcut, QDropEvent, QDragEnterEvent

from .config import Config
from .parser import Cue, format_ms_to_timestamp
from .playback import PlaybackEngine
from .overlay import OverlayWindow


DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Ubuntu', sans-serif;
    font-size: 13px;
}

QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #181825;
    border-radius: 8px;
    padding: 8px;
}

QTabBar::tab {
    background-color: #1e1e2e;
    color: #a6adc8;
    padding: 8px 16px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background-color: #181825;
    color: #f38ba8;
    border-bottom: 2px solid #e95420;
    color: #ffffff;
}

QTabBar::tab:hover {
    color: #ffffff;
    background-color: #313244;
}

QGroupBox {
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 18px;
    font-weight: bold;
    color: #fab387;
    padding-top: 16px;
    background-color: #181825;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
}

QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #45475a;
    color: #ffffff;
    border-color: #585b70;
}

QPushButton:pressed {
    background-color: #e95420;
    color: #ffffff;
}

QPushButton:disabled {
    background-color: #1e1e2e;
    color: #6c7086;
    border-color: #313244;
}

QPushButton#btn_primary {
    background-color: #e95420;
    color: #ffffff;
    border: none;
    font-weight: bold;
}

QPushButton#btn_primary:hover {
    background-color: #ff6e3a;
}

QPushButton#btn_play {
    background-color: #a6e3a1;
    color: #11111b;
    border: none;
    font-size: 15px;
    font-weight: bold;
    padding: 8px 18px;
}

QPushButton#btn_play:hover {
    background-color: #bbf2b6;
}

QPushButton#btn_lock_action {
    padding: 8px 14px;
    font-weight: bold;
    font-size: 13px;
    border-radius: 6px;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #313244;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #e95420;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #e95420;
    width: 14px;
    margin-top: -4px;
    margin-bottom: -4px;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background: #ffaa88;
}

QTableWidget {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 6px;
    gridline-color: #1e1e2e;
    selection-background-color: #e95420;
    selection-color: #ffffff;
}

QTableWidget::item {
    padding: 4px;
}

QHeaderView::section {
    background-color: #181825;
    color: #a6adc8;
    padding: 6px;
    border: 1px solid #313244;
    font-weight: bold;
}

QLineEdit {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
}

QLineEdit:focus {
    border-color: #e95420;
}

QComboBox, QFontComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 5px 10px;
}

QComboBox:drop-down, QFontComboBox:drop-down {
    border: none;
}

QCheckBox {
    spacing: 8px;
    color: #cdd6f4;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #45475a;
    background: #313244;
}

QCheckBox::indicator:checked {
    background-color: #e95420;
    border-color: #e95420;
}
"""


class ControllerWindow(QMainWindow):
    def __init__(self, config: Config, engine: PlaybackEngine, overlay: OverlayWindow, parent=None):
        super().__init__(parent)
        self.config = config
        self.engine = engine
        self.overlay = overlay

        self._slider_dragging = False
        self._highlighting_table = False

        self.setAcceptDrops(True)
        self._init_window()
        self._init_ui()
        self._connect_signals()
        self._setup_shortcuts()

        # Load last opened file or sample if available
        last_file = self.config.get("last_file", "")
        if last_file and os.path.isfile(last_file):
            self.load_subtitle_file(last_file)
        else:
            # Check for bundled sample
            sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "sample.srt")
            if os.path.isfile(sample_path):
                self.load_subtitle_file(sample_path)

    def _init_window(self):
        self.setWindowTitle("SubtitlesOnScreen — Panel de Control")
        self.setStyleSheet(DARK_STYLESHEET)

        # Set window icon
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        w = self.config.get("controller_width", 780)
        h = self.config.get("controller_height", 560)
        x = self.config.get("controller_x", -1)
        y = self.config.get("controller_y", -1)

        if x > 0 and y > 0:
            self.setGeometry(x, y, w, h)
        else:
            self.resize(w, h)
            # Center on screen
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.move((geo.width() - w) // 2, (geo.height() - h) // 4)

        if self.config.get("controller_always_on_top", False):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    def _init_ui(self):
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # --- Top Header Bar ---
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        # File Load Button
        self.btn_load_file = QPushButton("📂 Cargar Subtítulo (.srt, .vtt)", self)
        self.btn_load_file.setObjectName("btn_primary")
        self.btn_load_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_file.clicked.connect(self._on_choose_file)

        # Sample Button
        self.btn_sample = QPushButton("🌟 Cargar Ejemplo", self)
        self.btn_sample.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sample.clicked.connect(self._on_load_sample)

        # Active File Label
        self.lbl_file_info = QLabel("Ningún archivo cargado", self)
        self.lbl_file_info.setStyleSheet("color: #a6adc8; font-weight: bold;")

        # Always on top checkbox for controller
        self.chk_always_on_top = QCheckBox("📌 Fijar Panel al frente", self)
        self.chk_always_on_top.setChecked(self.config.get("controller_always_on_top", False))
        self.chk_always_on_top.toggled.connect(self._on_toggle_always_on_top)

        header_layout.addWidget(self.btn_load_file)
        header_layout.addWidget(self.btn_sample)
        header_layout.addWidget(self.lbl_file_info, 1)
        header_layout.addWidget(self.chk_always_on_top)

        main_layout.addLayout(header_layout)

        # --- Click-Through Mode Status Bar ---
        self.status_frame = QFrame(self)
        self.status_frame.setObjectName("status_frame")
        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(12, 8, 12, 8)
        status_layout.setSpacing(12)

        self.lbl_mode_indicator = QLabel("● Modo: Edición (Arrastra y redimensiona los subtítulos)", self)
        self.lbl_mode_indicator.setStyleSheet("font-weight: bold; font-size: 13px; color: #fab387;")

        self.lbl_shortcut_hint = QLabel("(Atajo global: Alt + Shift + L)", self)
        self.lbl_shortcut_hint.setStyleSheet("color: #6c7086; font-size: 12px;")

        self.btn_toggle_lock = QPushButton("🔒 Activar Modo Click-Through", self)
        self.btn_toggle_lock.setObjectName("btn_lock_action")
        self.btn_toggle_lock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_lock.setStyleSheet("""
            QPushButton {
                background-color: #e95420;
                color: #ffffff;
                border: none;
            }
            QPushButton:hover {
                background-color: #ff6e3a;
            }
        """)
        self.btn_toggle_lock.clicked.connect(self._on_toggle_lock)

        self.btn_toggle_overlay = QPushButton("👁 Ocultar Subtítulos", self)
        self.btn_toggle_overlay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_overlay.clicked.connect(self._on_toggle_overlay_visibility)

        status_layout.addWidget(self.lbl_mode_indicator)
        status_layout.addWidget(self.lbl_shortcut_hint)
        status_layout.addStretch()
        status_layout.addWidget(self.btn_toggle_overlay)
        status_layout.addWidget(self.btn_toggle_lock)

        self.status_frame.setStyleSheet("""
            QFrame#status_frame {
                background-color: #11111b;
                border: 1px solid #313244;
                border-radius: 8px;
            }
        """)
        main_layout.addWidget(self.status_frame)

        # --- Tabs Container ---
        self.tabs = QTabWidget(self)
        self.tab_playback = QWidget()
        self.tab_explorer = QWidget()
        self.tab_appearance = QWidget()
        self.tab_shortcuts = QWidget()

        self._init_playback_tab()
        self._init_explorer_tab()
        self._init_appearance_tab()
        self._init_shortcuts_tab()

        self.tabs.addTab(self.tab_playback, "▶ Control de Reproducción")
        self.tabs.addTab(self.tab_explorer, "📑 Diálogos y Búsqueda")
        self.tabs.addTab(self.tab_appearance, "🎨 Estilo y Apariencia")
        self.tabs.addTab(self.tab_shortcuts, "⌨ Atajos de Teclado")

        main_layout.addWidget(self.tabs, 1)

    def _init_playback_tab(self):
        layout = QVBoxLayout(self.tab_playback)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Timeline Scrubber
        timeline_box = QGroupBox("Línea de Tiempo", self.tab_playback)
        tl_layout = QVBoxLayout(timeline_box)

        time_header = QHBoxLayout()
        self.lbl_current_time = QLabel("00:00:00", timeline_box)
        self.lbl_current_time.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")

        self.lbl_total_time = QLabel("/ 00:00:00", timeline_box)
        self.lbl_total_time.setStyleSheet("font-size: 16px; color: #a6adc8;")

        time_header.addWidget(self.lbl_current_time)
        time_header.addWidget(self.lbl_total_time)
        time_header.addStretch()

        self.timeline_slider = QSlider(Qt.Orientation.Horizontal, timeline_box)
        self.timeline_slider.setRange(0, 1000)
        self.timeline_slider.setValue(0)
        self.timeline_slider.sliderPressed.connect(self._on_slider_pressed)
        self.timeline_slider.sliderMoved.connect(self._on_slider_moved)
        self.timeline_slider.sliderReleased.connect(self._on_slider_released)

        tl_layout.addLayout(time_header)
        tl_layout.addWidget(self.timeline_slider)
        layout.addWidget(timeline_box)

        # Main Transport Controls
        transport_box = QGroupBox("Controles de Reproducción", self.tab_playback)
        tr_layout = QHBoxLayout(transport_box)
        tr_layout.setSpacing(8)

        self.btn_prev_cue = QPushButton("⏮ Anterior", transport_box)
        self.btn_prev_cue.setToolTip("Saltar al subtítulo anterior (Alt + Shift + Up)")
        self.btn_prev_cue.clicked.connect(self.engine.previous_cue)

        self.btn_rewind_5 = QPushButton("⏪ -5s", transport_box)
        self.btn_rewind_5.setToolTip("Retroceder 5 segundos (Alt + Shift + Left)")
        self.btn_rewind_5.clicked.connect(lambda: self.engine.seek_relative(-5000))

        self.btn_play = QPushButton("▶ Reproducir", transport_box)
        self.btn_play.setObjectName("btn_play")
        self.btn_play.setToolTip("Reproducir / Pausar (Espacio o Alt + Shift + P)")
        self.btn_play.clicked.connect(self.engine.toggle_play)

        self.btn_stop = QPushButton("⏹ Detener", transport_box)
        self.btn_stop.clicked.connect(self.engine.stop)

        self.btn_forward_5 = QPushButton("+5s ⏩", transport_box)
        self.btn_forward_5.setToolTip("Adelantar 5 segundos (Alt + Shift + Right)")
        self.btn_forward_5.clicked.connect(lambda: self.engine.seek_relative(5000))

        self.btn_next_cue = QPushButton("Siguiente ⏭", transport_box)
        self.btn_next_cue.setToolTip("Saltar al siguiente subtítulo (Alt + Shift + Down)")
        self.btn_next_cue.clicked.connect(self.engine.next_cue)

        tr_layout.addWidget(self.btn_prev_cue)
        tr_layout.addWidget(self.btn_rewind_5)
        tr_layout.addWidget(self.btn_play, 1)
        tr_layout.addWidget(self.btn_stop)
        tr_layout.addWidget(self.btn_forward_5)
        tr_layout.addWidget(self.btn_next_cue)
        layout.addWidget(transport_box)

        # Bottom Row: Speed & Sync Offset
        bottom_row = QHBoxLayout()

        # Speed Box
        speed_box = QGroupBox("Velocidad de Reproducción", self.tab_playback)
        speed_layout = QHBoxLayout(speed_box)
        speed_layout.setSpacing(4)

        for spd in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
            btn = QPushButton(f"{spd}x", speed_box)
            btn.setCheckable(True)
            if spd == 1.0:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, s=spd: self._on_speed_selected(s))
            speed_layout.addWidget(btn)

        self.speed_buttons = speed_box.findChildren(QPushButton)
        bottom_row.addWidget(speed_box, 1)

        # Audio Sync Offset Box
        sync_box = QGroupBox("Sincronización de Audio (Offset)", self.tab_playback)
        sync_layout = QVBoxLayout(sync_box)

        offset_info_layout = QHBoxLayout()
        self.lbl_offset_val = QLabel("Desfase: 0 ms", sync_box)
        self.lbl_offset_val.setStyleSheet("font-weight: bold; color: #a6e3a1; font-size: 14px;")
        offset_info_layout.addWidget(self.lbl_offset_val)
        offset_info_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_m500 = QPushButton("-500 ms", sync_box)
        btn_m500.clicked.connect(lambda: self.engine.add_offset(-500))

        btn_m100 = QPushButton("-100 ms", sync_box)
        btn_m100.clicked.connect(lambda: self.engine.add_offset(-100))

        btn_reset_offset = QPushButton("Restablecer (0)", sync_box)
        btn_reset_offset.clicked.connect(self.engine.reset_offset)

        btn_p100 = QPushButton("+100 ms", sync_box)
        btn_p100.clicked.connect(lambda: self.engine.add_offset(100))

        btn_p500 = QPushButton("+500 ms", sync_box)
        btn_p500.clicked.connect(lambda: self.engine.add_offset(500))

        btn_row.addWidget(btn_m500)
        btn_row.addWidget(btn_m100)
        btn_row.addWidget(btn_reset_offset)
        btn_row.addWidget(btn_p100)
        btn_row.addWidget(btn_p500)

        sync_layout.addLayout(offset_info_layout)
        sync_layout.addLayout(btn_row)
        bottom_row.addWidget(sync_box, 1)

        layout.addLayout(bottom_row)
        layout.addStretch()

    def _init_explorer_tab(self):
        layout = QVBoxLayout(self.tab_explorer)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Search Bar
        search_layout = QHBoxLayout()
        self.txt_search = QLineEdit(self.tab_explorer)
        self.txt_search.setPlaceholderText("🔍 Filtrar subtítulos por texto...")
        self.txt_search.textChanged.connect(self._on_search_text_changed)

        self.btn_clear_search = QPushButton("✕ Limpiar", self.tab_explorer)
        self.btn_clear_search.clicked.connect(self.txt_search.clear)

        search_layout.addWidget(self.txt_search, 1)
        search_layout.addWidget(self.btn_clear_search)
        layout.addLayout(search_layout)

        # Dialogue Table
        self.table_cues = QTableWidget(self.tab_explorer)
        self.table_cues.setColumnCount(3)
        self.table_cues.setHorizontalHeaderLabels(["#", "Tiempo", "Subtítulo / Diálogo"])
        self.table_cues.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_cues.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_cues.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_cues.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_cues.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_cues.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_cues.cellDoubleClicked.connect(self._on_cue_double_clicked)
        self.table_cues.cellClicked.connect(self._on_cue_double_clicked)

        layout.addWidget(self.table_cues, 1)

    def _init_appearance_tab(self):
        layout = QVBoxLayout(self.tab_appearance)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Grid of settings
        grid = QGridLayout()
        grid.setSpacing(10)

        # 1. Font Family & Size
        lbl_font = QLabel("Tipografía / Fuente:", self.tab_appearance)
        self.font_combo = QFontComboBox(self.tab_appearance)
        cur_font = self.config.get("font_family", "Ubuntu")
        self.font_combo.setCurrentFont(QFont(cur_font))
        self.font_combo.currentFontChanged.connect(self._on_font_family_changed)

        lbl_size = QLabel("Tamaño de Fuente:", self.tab_appearance)
        size_layout = QHBoxLayout()
        self.slider_font_size = QSlider(Qt.Orientation.Horizontal, self.tab_appearance)
        self.slider_font_size.setRange(14, 64)
        self.slider_font_size.setValue(self.config.get("font_size", 28))
        self.lbl_font_size_val = QLabel(f"{self.slider_font_size.value()} pt", self.tab_appearance)
        self.lbl_font_size_val.setFixedWidth(45)
        self.slider_font_size.valueChanged.connect(self._on_font_size_changed)
        size_layout.addWidget(self.slider_font_size, 1)
        size_layout.addWidget(self.lbl_font_size_val)

        # Bold & Italic
        style_layout = QHBoxLayout()
        self.chk_bold = QCheckBox("Negrita (Bold)", self.tab_appearance)
        self.chk_bold.setChecked(self.config.get("font_bold", True))
        self.chk_bold.toggled.connect(self._on_font_bold_toggled)

        self.chk_italic = QCheckBox("Cursiva (Italic)", self.tab_appearance)
        self.chk_italic.setChecked(self.config.get("font_italic", False))
        self.chk_italic.toggled.connect(self._on_font_italic_toggled)
        style_layout.addWidget(self.chk_bold)
        style_layout.addWidget(self.chk_italic)

        # 2. Text Color & Presets
        lbl_color = QLabel("Color del Texto:", self.tab_appearance)
        color_layout = QHBoxLayout()
        self.btn_text_color = QPushButton("⬛ Seleccionar Color...", self.tab_appearance)
        self.btn_text_color.clicked.connect(self._on_pick_text_color)
        self._update_color_button(self.btn_text_color, self.config.get("text_color", "#FFFFFF"))

        # Preset color buttons
        color_layout.addWidget(self.btn_text_color)
        for name, hex_col in [("Blanco", "#FFFFFF"), ("Amarillo", "#FFE066"), ("Cian", "#66D9EF"), ("Verde", "#A6E22E")]:
            btn_col = QPushButton(name, self.tab_appearance)
            btn_col.setStyleSheet(f"background-color: {hex_col}; color: #000000; font-weight: bold; border-radius: 4px; padding: 4px 8px;")
            btn_col.clicked.connect(lambda ch, c=hex_col: self._set_text_color(c))
            color_layout.addWidget(btn_col)

        # 3. Outline / Stroke
        lbl_outline = QLabel("Contorno / Sombra:", self.tab_appearance)
        outline_layout = QHBoxLayout()
        self.chk_outline = QCheckBox("Activar Contorno", self.tab_appearance)
        self.chk_outline.setChecked(self.config.get("outline_enabled", True))
        self.chk_outline.toggled.connect(self._on_outline_toggled)

        self.slider_outline = QSlider(Qt.Orientation.Horizontal, self.tab_appearance)
        self.slider_outline.setRange(0, 6)
        self.slider_outline.setValue(self.config.get("outline_width", 3))
        self.slider_outline.valueChanged.connect(self._on_outline_width_changed)

        outline_layout.addWidget(self.chk_outline)
        outline_layout.addWidget(QLabel("Grosor:"))
        outline_layout.addWidget(self.slider_outline, 1)

        # 4. Background Style & Opacity
        lbl_bg = QLabel("Fondo de Subtítulos:", self.tab_appearance)
        bg_layout = QHBoxLayout()
        self.combo_bg_style = QComboBox(self.tab_appearance)
        self.combo_bg_style.addItems(["Caja redondeada", "Banda completa", "Sin fondo"])
        style_map = {"rounded_box": 0, "banner": 1, "none": 2}
        self.combo_bg_style.setCurrentIndex(style_map.get(self.config.get("background_style", "rounded_box"), 0))
        self.combo_bg_style.currentIndexChanged.connect(self._on_bg_style_changed)

        lbl_opacity = QLabel("Opacidad del Fondo:")
        self.slider_bg_opacity = QSlider(Qt.Orientation.Horizontal, self.tab_appearance)
        self.slider_bg_opacity.setRange(0, 100)
        self.slider_bg_opacity.setValue(int(self.config.get("background_opacity", 0.65) * 100))
        self.lbl_opacity_val = QLabel(f"{self.slider_bg_opacity.value()}%", self.tab_appearance)
        self.lbl_opacity_val.setFixedWidth(40)
        self.slider_bg_opacity.valueChanged.connect(self._on_bg_opacity_changed)

        bg_layout.addWidget(self.combo_bg_style)
        bg_layout.addWidget(lbl_opacity)
        bg_layout.addWidget(self.slider_bg_opacity, 1)
        bg_layout.addWidget(self.lbl_opacity_val)

        # 5. Position Presets
        lbl_pos = QLabel("Posición en Pantalla:", self.tab_appearance)
        pos_layout = QHBoxLayout()
        btn_pos_bottom = QPushButton("⬇ Abajo Centro", self.tab_appearance)
        btn_pos_bottom.clicked.connect(lambda: self.overlay.set_position_preset("bottom_center"))

        btn_pos_top = QPushButton("⬆ Arriba Centro", self.tab_appearance)
        btn_pos_top.clicked.connect(lambda: self.overlay.set_position_preset("top_center"))

        btn_pos_center = QPushButton("↕ Centro Pantalla", self.tab_appearance)
        btn_pos_center.clicked.connect(lambda: self.overlay.set_position_preset("center"))

        pos_layout.addWidget(btn_pos_bottom)
        pos_layout.addWidget(btn_pos_top)
        pos_layout.addWidget(btn_pos_center)

        # Assemble Grid
        row = 0
        grid.addWidget(lbl_font, row, 0); grid.addWidget(self.font_combo, row, 1); row += 1
        grid.addWidget(lbl_size, row, 0); grid.addLayout(size_layout, row, 1); row += 1
        grid.addWidget(QLabel("Estilo:"), row, 0); grid.addLayout(style_layout, row, 1); row += 1
        grid.addWidget(lbl_color, row, 0); grid.addLayout(color_layout, row, 1); row += 1
        grid.addWidget(lbl_outline, row, 0); grid.addLayout(outline_layout, row, 1); row += 1
        grid.addWidget(lbl_bg, row, 0); grid.addLayout(bg_layout, row, 1); row += 1
        grid.addWidget(lbl_pos, row, 0); grid.addLayout(pos_layout, row, 1); row += 1

        layout.addLayout(grid)
        layout.addStretch()

    def _init_shortcuts_tab(self):
        layout = QVBoxLayout(self.tab_shortcuts)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        info = QLabel(
            "<h3>Atajos de Teclado Globales (Funcionan sobre cualquier ventana / aplicación)</h3>"
            "<p>Puedes usar estos atajos incluso si estás viendo un video en pantalla completa en el navegador, VLC o cualquier otro programa:</p>"
            "<table style='width:100%; border-collapse: collapse; margin-top:8px;'>"
            "<tr style='background-color:#11111b; color:#fab387; font-weight:bold;'>"
            "<th style='padding:8px; border:1px solid #313244; text-align:left;'>Acción</th>"
            "<th style='padding:8px; border:1px solid #313244; text-align:left;'>Atajo Global</th>"
            "<th style='padding:8px; border:1px solid #313244; text-align:left;'>Atajo en Panel</th>"
            "</tr>"
            "<tr><td style='padding:8px; border:1px solid #313244;'><b>Reproducir / Pausar</b></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Alt + Shift + P</code></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Espacio</code></td></tr>"
            "<tr><td style='padding:8px; border:1px solid #313244;'><b>Bloquear / Desbloquear Modo Click-Through</b></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Alt + Shift + L</code></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Ctrl + L</code></td></tr>"
            "<tr><td style='padding:8px; border:1px solid #313244;'><b>Retroceder 5 segundos</b></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Alt + Shift + Flecha Izquierda</code></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Flecha Izquierda</code></td></tr>"
            "<tr><td style='padding:8px; border:1px solid #313244;'><b>Adelantar 5 segundos</b></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Alt + Shift + Flecha Derecha</code></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Flecha Derecha</code></td></tr>"
            "<tr><td style='padding:8px; border:1px solid #313244;'><b>Subtítulo Anterior / Siguiente</b></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Alt + Shift + Arriba / Abajo</code></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Arriba / Abajo</code></td></tr>"
            "<tr><td style='padding:8px; border:1px solid #313244;'><b>Calibrar Retraso (-100ms / +100ms)</b></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>Alt + Shift + [ / ]</code></td>"
            "<td style='padding:8px; border:1px solid #313244;'><code>[ / ]</code></td></tr>"
            "</table>"
            "<br/>"
            "<h4>Interacción con el Ratón sobre los Subtítulos (Modo Edición):</h4>"
            "<ul>"
            "<li><b>Arrastrar:</b> Mueve la caja de subtítulos a cualquier lugar de la pantalla.</li>"
            "<li><b>Bordes y esquinas:</b> Cambia el tamaño del área de subtítulos.</li>"
            "<li><b>Rueda del ratón:</b> Aumenta o disminuye el tamaño de la letra.</li>"
            "<li><b>Doble clic:</b> Bloquea instantáneamente en modo Click-Through.</li>"
            "</ul>",
            self.tab_shortcuts
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch()

    def _connect_signals(self):
        # Engine Signals
        self.engine.sig_cue_changed.connect(self._on_cue_changed)
        self.engine.sig_time_updated.connect(self._on_time_updated)
        self.engine.sig_state_changed.connect(self._on_state_changed)
        self.engine.sig_offset_changed.connect(self._on_offset_changed)
        self.engine.sig_file_loaded.connect(self._on_file_loaded)

        # Overlay Signals
        self.overlay.sig_lock_toggled.connect(self._on_overlay_lock_toggled)
        self.overlay.sig_font_size_changed.connect(self._on_overlay_font_size_changed)
        self.overlay.sig_request_panel.connect(self.show_and_raise)

    def _setup_shortcuts(self):
        # Space for Play/Pause in Controller
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.engine.toggle_play)
        # Left/Right for Seek ±5s
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self.engine.seek_relative(-5000))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self.engine.seek_relative(5000))
        # Up/Down for Prev/Next Cue
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, activated=self.engine.previous_cue)
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, activated=self.engine.next_cue)
        # [ and ] for Offset ±100ms
        QShortcut(QKeySequence(Qt.Key.Key_BracketLeft), self, activated=lambda: self.engine.add_offset(-100))
        QShortcut(QKeySequence(Qt.Key.Key_BracketRight), self, activated=lambda: self.engine.add_offset(100))
        # Ctrl+L to toggle lock
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._on_toggle_lock)

    # --- Actions & Handlers ---

    def show_and_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_choose_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo de subtítulos",
            os.path.expanduser("~"),
            "Archivos de Subtítulos (*.srt *.vtt *.sub);;Todos los archivos (*)"
        )
        if filepath:
            self.load_subtitle_file(filepath)

    def _on_load_sample(self):
        sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "sample.srt")
        if os.path.isfile(sample_path):
            self.load_subtitle_file(sample_path)
        else:
            QMessageBox.warning(self, "Aviso", "No se encontró el archivo de ejemplo.")

    def load_subtitle_file(self, filepath: str):
        success = self.engine.load_file(filepath)
        if success:
            self.config.set("last_file", filepath)
            self._populate_explorer()

    def _populate_explorer(self):
        sub = self.engine.sub_file
        if not sub:
            return

        self.table_cues.setRowCount(0)
        cues = sub.cues
        self.table_cues.setRowCount(len(cues))

        for row, cue in enumerate(cues):
            item_num = QTableWidgetItem(str(cue.index))
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_time = QTableWidgetItem(f"{format_ms_to_timestamp(cue.start_ms, False)} - {format_ms_to_timestamp(cue.end_ms, False)}")
            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_text = QTableWidgetItem(cue.text)

            # Store cue object in UserRole
            item_num.setData(Qt.ItemDataRole.UserRole, cue)

            self.table_cues.setItem(row, 0, item_num)
            self.table_cues.setItem(row, 1, item_time)
            self.table_cues.setItem(row, 2, item_text)

    def _on_cue_double_clicked(self, row: int, col: int):
        item = self.table_cues.item(row, 0)
        if item:
            cue: Optional[Cue] = item.data(Qt.ItemDataRole.UserRole)
            if cue:
                self.engine.seek(cue.start_ms)

    def _on_search_text_changed(self, text: str):
        text = text.lower().strip()
        for row in range(self.table_cues.rowCount()):
            if not text:
                self.table_cues.setRowHidden(row, False)
                continue
            item = self.table_cues.item(row, 2)
            if item and text in item.text().lower():
                self.table_cues.setRowHidden(row, False)
            else:
                self.table_cues.setRowHidden(row, True)

    def _on_file_loaded(self, filepath: str, count: int, duration_ms: int):
        filename = os.path.basename(filepath)
        dur_str = format_ms_to_timestamp(duration_ms, show_millis=False)
        self.lbl_file_info.setText(f"📄 {filename}  ({count} subtítulos — {dur_str})")
        self.lbl_total_time.setText(f"/ {dur_str}")
        self.timeline_slider.setRange(0, max(1, duration_ms))
        self.timeline_slider.setValue(0)

    def _on_cue_changed(self, cue: Optional[Cue]):
        self.overlay.set_cue(cue)

        # Highlight current cue in table if explorer tab visible
        if cue and not self._highlighting_table:
            self._highlighting_table = True
            row = cue.index - 1
            if 0 <= row < self.table_cues.rowCount():
                self.table_cues.selectRow(row)
                if not self.table_cues.isRowHidden(row):
                    self.table_cues.scrollToItem(self.table_cues.item(row, 0))
            self._highlighting_table = False

    def _on_time_updated(self, current_ms: int, total_ms: int, formatted_str: str):
        cur_str = format_ms_to_timestamp(current_ms, show_millis=False)
        self.lbl_current_time.setText(cur_str)
        if not self._slider_dragging:
            self.timeline_slider.blockSignals(True)
            self.timeline_slider.setValue(current_ms)
            self.timeline_slider.blockSignals(False)

    def _on_state_changed(self, is_playing: bool):
        if is_playing:
            self.btn_play.setText("⏸ Pausar")
            self.btn_play.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold;")
        else:
            self.btn_play.setText("▶ Reproducir")
            self.btn_play.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")

    def _on_offset_changed(self, offset_ms: int):
        sign = "+" if offset_ms >= 0 else ""
        self.lbl_offset_val.setText(f"Desfase: {sign}{offset_ms} ms")
        self.config.set("sync_offset_ms", offset_ms)

    def _on_speed_selected(self, speed: float):
        self.engine.set_speed(speed)
        for btn in self.speed_buttons:
            btn.setChecked(btn.text() == f"{speed}x")

    def _on_slider_pressed(self):
        self._slider_dragging = True

    def _on_slider_moved(self, value: int):
        self.lbl_current_time.setText(format_ms_to_timestamp(value, show_millis=False))

    def _on_slider_released(self):
        self._slider_dragging = False
        self.engine.seek(self.timeline_slider.value())

    # --- Mode & Overlay Toggles ---

    def _on_toggle_lock(self):
        new_state = not self.overlay.is_locked
        self.overlay.set_locked(new_state)

    def _on_overlay_lock_toggled(self, is_locked: bool):
        if is_locked:
            self.lbl_mode_indicator.setText("● Modo: Click-Through ACTIVO (El ratón traspasa los subtítulos)")
            self.lbl_mode_indicator.setStyleSheet("font-weight: bold; font-size: 13px; color: #a6e3a1;")
            self.btn_toggle_lock.setText("🔓 Desbloquear Modo Edición")
            self.btn_toggle_lock.setStyleSheet("""
                QPushButton {
                    background-color: #45475a;
                    color: #cdd6f4;
                    border: 1px solid #585b70;
                }
                QPushButton:hover {
                    background-color: #585b70;
                    color: #ffffff;
                }
            """)
        else:
            self.lbl_mode_indicator.setText("● Modo: Edición (Arrastra y redimensiona los subtítulos)")
            self.lbl_mode_indicator.setStyleSheet("font-weight: bold; font-size: 13px; color: #fab387;")
            self.btn_toggle_lock.setText("🔒 Activar Modo Click-Through")
            self.btn_toggle_lock.setStyleSheet("""
                QPushButton {
                    background-color: #e95420;
                    color: #ffffff;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #ff6e3a;
                }
            """)

    def _on_toggle_overlay_visibility(self):
        if self.overlay.isVisible():
            self.overlay.hide()
            self.btn_toggle_overlay.setText("👁 Mostrar Subtítulos")
        else:
            self.overlay.show()
            self.btn_toggle_overlay.setText("👁 Ocultar Subtítulos")

    def _on_toggle_always_on_top(self, checked: bool):
        self.config.set("controller_always_on_top", checked)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    # --- Appearance Handlers ---

    def _on_font_family_changed(self, font: QFont):
        self.config.set("font_family", font.family())
        self.overlay.apply_config()

    def _on_font_size_changed(self, val: int):
        self.lbl_font_size_val.setText(f"{val} pt")
        self.config.set("font_size", val)
        self.overlay.apply_config()

    def _on_overlay_font_size_changed(self, new_size: int):
        self.slider_font_size.blockSignals(True)
        self.slider_font_size.setValue(new_size)
        self.lbl_font_size_val.setText(f"{new_size} pt")
        self.slider_font_size.blockSignals(False)

    def _on_font_bold_toggled(self, val: bool):
        self.config.set("font_bold", val)
        self.overlay.apply_config()

    def _on_font_italic_toggled(self, val: bool):
        self.config.set("font_italic", val)
        self.overlay.apply_config()

    def _on_pick_text_color(self):
        cur_hex = self.config.get("text_color", "#FFFFFF")
        color = QColorDialog.getColor(QColor(cur_hex), self, "Seleccionar Color de Texto")
        if color.isValid():
            self._set_text_color(color.name())

    def _set_text_color(self, hex_color: str):
        self.config.set("text_color", hex_color)
        self._update_color_button(self.btn_text_color, hex_color)
        self.overlay.apply_config()

    def _update_color_button(self, btn: QPushButton, hex_color: str):
        btn.setStyleSheet(f"background-color: {hex_color}; color: #000000; font-weight: bold; border-radius: 4px; padding: 4px 10px;")

    def _on_outline_toggled(self, val: bool):
        self.config.set("outline_enabled", val)
        self.overlay.apply_config()

    def _on_outline_width_changed(self, val: int):
        self.config.set("outline_width", val)
        self.overlay.apply_config()

    def _on_bg_style_changed(self, idx: int):
        styles = ["rounded_box", "banner", "none"]
        if 0 <= idx < len(styles):
            self.config.set("background_style", styles[idx])
            self.overlay.apply_config()

    def _on_bg_opacity_changed(self, val: int):
        self.lbl_opacity_val.setText(f"{val}%")
        self.config.set("background_opacity", val / 100.0)
        self.overlay.apply_config()

    # --- Drag & Drop Subtitle Files ---

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".srt", ".vtt", ".sub")):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith((".srt", ".vtt", ".sub")):
                self.load_subtitle_file(filepath)
                event.acceptProposedAction()
                break

    def closeEvent(self, event):
        """Save geometry and let the application orchestrator handle exit/tray."""
        self.config.set("controller_width", self.width(), auto_save=False)
        self.config.set("controller_height", self.height(), auto_save=False)
        self.config.set("controller_x", self.x(), auto_save=False)
        self.config.set("controller_y", self.y(), auto_save=True)
        super().closeEvent(event)
