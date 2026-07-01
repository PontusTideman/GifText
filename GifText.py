#!/usr/bin/env python3
"""
GifText v1.5.1 - Animated GIF Text Editor
Full-featured meme text animator with keyframe animation, onion skinning,
undo/redo, project save/load, drag-resize, text presets, and more.
"""

import multiprocessing
multiprocessing.freeze_support()

import sys
import os
import json
from datetime import datetime
from pathlib import Path


def _branding_icon_path() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "icon.png")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "icon.png")
    current = Path(__file__).resolve()
    candidates.extend([current.parent / "icon.png", current.parent.parent / "icon.png", current.parent.parent.parent / "icon.png"])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path("icon.png")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QSpinBox, QDoubleSpinBox, QComboBox,
    QColorDialog, QFileDialog, QFrame, QSplitter, QCheckBox,
    QFontComboBox, QGroupBox, QGridLayout, QSizePolicy, QScrollArea,
    QPlainTextEdit, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal, QSize, QThread
from PyQt6.QtGui import (
    QIcon, QPixmap, QImage, QColor, QPainter, QFont, QPen,
    QFontMetrics, QPainterPath, QCursor, QAction, QLinearGradient
)
from PIL import Image

from animation import (
    EASING_CURVES,
    _normalize_path_points,
    apply_easing_curve,
    apply_staggered_text,
    build_effect_keyframes,
    build_path_keyframes,
    sample_cubic_path,
)
from models import (
    LAYER_COLORS,
    MEME_PRESETS,
    PROJECT_SCHEMA_VERSION,
    VERSION,
    TextKeyframe,
    TextLayer,
    UndoManager,
)
from rendering import (
    UNICODE_FALLBACK_FONTS,
    get_pil_font,
    register_custom_font,
    render_text_pil,
)
from project import (
    ProjectValidationError,
    build_project_payload,
    parse_subtitle_text,
    subtitle_entries_to_layers,
    validate_project_payload,
)
from diagnostics import (
    DiagnosticsRecorder,
    build_diagnostics_bundle,
)
from workers import (
    CancelableWorker,
    ExportWorker,
    HAS_IMAGEIO,
    LoadGifWorker,
    LoadVideoWorker,
    TrackingWorker,
    VIDEO_EXTENSIONS,
    get_video_metadata,
)




DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #eef2f7;
    font-family: "Segoe UI";
    font-size: 13px;
}
QWidget#appRoot {
    background-color: #0d1117;
}
QFrame#workspaceHeader,
QFrame#commandBar,
QFrame#timeline,
QFrame#canvasShell,
QFrame#panelHeader {
    background-color: #151b24;
    border: 1px solid #273142;
    border-radius: 14px;
}
QFrame#commandBar {
    background-color: #121821;
}
QFrame#canvasShell {
    background-color: #121821;
}
QFrame#panelHeader {
    padding: 10px 12px;
}
QLabel#appTitle {
    font-size: 22px;
    font-weight: 700;
    color: #f7fafc;
}
QLabel#appSubtitle {
    color: #9ca7b8;
    font-size: 12px;
}
QLabel#workspaceMeta {
    color: #c2d0e6;
    font-size: 12px;
    font-weight: 600;
}
QLabel#workspaceHint {
    color: #8d99ab;
    font-size: 11px;
}
QLabel#panelTitle {
    font-size: 17px;
    font-weight: 700;
    color: #f7fafc;
}
QLabel#panelSubtitle,
QLabel#sectionNote {
    color: #97a3b6;
    font-size: 11px;
}
QFrame#selectionCard {
    background-color: #111720;
    border: 1px solid #2a3446;
    border-radius: 14px;
}
QLabel#selectionEyebrow {
    color: #97a3b6;
    font-size: 10px;
    font-weight: 700;
}
QLabel#selectionTitle {
    color: #f7fafc;
    font-size: 18px;
    font-weight: 700;
}
QLabel#selectionMeta {
    color: #b2c0d6;
    font-size: 11px;
}
QLabel#selectionState {
    color: #76b0ff;
    font-size: 11px;
    font-weight: 600;
}
QPushButton {
    background-color: #1a2230;
    color: #eef2f7;
    border: 1px solid #2a3446;
    border-radius: 12px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #212b3a;
    border-color: #3b4a63;
}
QPushButton:pressed {
    background-color: #253041;
}
QPushButton:disabled {
    background-color: #111720;
    color: #5c687b;
    border-color: #202734;
}
QPushButton#accent {
    background-color: #5ea2ff;
    color: #081019;
    border: 1px solid #5ea2ff;
}
QPushButton#accent:hover {
    background-color: #77b1ff;
    border-color: #77b1ff;
}
QPushButton#ghost {
    background-color: transparent;
    color: #b7c3d8;
    border-color: #2a3446;
}
QPushButton#ghost:hover {
    background-color: #141a23;
}
QPushButton#transport {
    min-width: 42px;
    max-width: 72px;
    border-radius: 10px;
}
QPushButton#layerAction {
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
    padding: 0;
    border-radius: 8px;
    font-size: 10px;
}
QPushButton#danger {
    background-color: #311921;
    color: #ffcad8;
    border-color: #6a3342;
}
QPushButton#danger:hover {
    background-color: #3b1f29;
}
QPushButton#keyframeSet {
    background-color: #1a2230;
    color: #eef2f7;
    border-color: #3d5f92;
}
QPushButton#keyframeSet:hover {
    background-color: #212b3a;
}
QPushButton#keyframeDel {
    background-color: #311921;
    color: #ffcad8;
    border-color: #6a3342;
}
QPushButton#preset {
    min-height: 34px;
    padding: 6px 10px;
    border-radius: 10px;
    font-size: 11px;
    color: #d8e2ef;
}
QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {
    background-color: #10161f;
    color: #f3f6fb;
    border: 1px solid #2a3446;
    border-radius: 10px;
    padding: 6px 10px;
    selection-background-color: #315f9e;
}
QPlainTextEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QComboBox:focus,
QFontComboBox:focus {
    border-color: #5ea2ff;
}
QPlainTextEdit {
    font-size: 14px;
    font-weight: 600;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #0f141b;
    border-radius: 999px;
}
QSlider::sub-page:horizontal {
    background: #5ea2ff;
    border-radius: 999px;
}
QSlider::handle:horizontal {
    background: #f3f6fb;
    border: 2px solid #5ea2ff;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}
QGroupBox {
    border: 1px solid #273142;
    border-radius: 14px;
    margin-top: 18px;
    padding: 16px 12px 12px 12px;
    font-weight: 700;
    color: #d9e2ef;
    background-color: #151b24;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #8cb6ff;
}
QScrollArea {
    border: none;
    background: transparent;
}
QLabel#frameLabel {
    font-size: 15px;
    font-weight: 700;
    color: #f3f6fb;
    min-width: 110px;
    background: #10161f;
    border: 1px solid #2a3446;
    border-radius: 10px;
    padding: 6px 10px;
}
QStatusBar {
    background-color: #0d1117;
    color: #8d99ab;
    font-size: 12px;
}
QCheckBox {
    spacing: 8px;
    color: #d2dbea;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid #364355;
    background: #10161f;
}
QCheckBox::indicator:checked {
    background: #5ea2ff;
    border-color: #5ea2ff;
}
QSplitter::handle {
    background: #151b24;
    width: 10px;
    margin: 10px 0;
}
QMenu {
    background-color: #151b24;
    color: #eef2f7;
    border: 1px solid #2a3446;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 6px 18px;
    border-radius: 6px;
}
QMenu::item:selected {
    background-color: #212b3a;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px;
}
QScrollBar::handle:vertical {
    background: #2a3446;
    min-height: 36px;
    border-radius: 5px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
"""


# ============================================================================
#  Data Models
# ============================================================================

class VideoImportDialog(QMessageBox):
    def __init__(self, parent, path, meta):
        super().__init__(parent)
        self.setWindowTitle("Import Video")
        self.setIcon(QMessageBox.Icon.Question)
        fps = meta.get("fps", 30)
        dur = meta.get("duration", 0)
        w, h = meta.get("size", (0, 0))
        self.setText(
            f"<b>{os.path.basename(path)}</b><br>"
            f"{w}x{h} | {fps:.1f} fps | {dur:.1f}s<br><br>"
            f"Import settings:"
        )

        grid = QWidget()
        layout = QGridLayout(grid)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Target FPS:"), 0, 0)
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 60)
        self.spin_fps.setValue(min(10, int(fps)))
        layout.addWidget(self.spin_fps, 0, 1)

        layout.addWidget(QLabel("Max frames:"), 1, 0)
        self.spin_max = QSpinBox()
        self.spin_max.setRange(2, 2000)
        self.spin_max.setValue(200)
        layout.addWidget(self.spin_max, 1, 1)

        layout.addWidget(QLabel("Max dimension (0=original):"), 2, 0)
        self.spin_size = QSpinBox()
        self.spin_size.setRange(0, 4096)
        self.spin_size.setValue(0)
        self.spin_size.setSingleStep(64)
        layout.addWidget(self.spin_size, 2, 1)

        layout.addWidget(QLabel("Trim start (s):"), 3, 0)
        self.spin_start = QDoubleSpinBox()
        self.spin_start.setRange(0, max(0, dur - 0.1))
        self.spin_start.setValue(0)
        self.spin_start.setDecimals(1)
        self.spin_start.setSingleStep(0.5)
        layout.addWidget(self.spin_start, 3, 1)

        layout.addWidget(QLabel("Trim end (s, 0=full):"), 4, 0)
        self.spin_end = QDoubleSpinBox()
        self.spin_end.setRange(0, dur)
        self.spin_end.setValue(0)
        self.spin_end.setDecimals(1)
        self.spin_end.setSingleStep(0.5)
        layout.addWidget(self.spin_end, 4, 1)

        self.layout().addWidget(grid, 1, 1)
        self.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

    def get_settings(self):
        return {
            "fps": self.spin_fps.value(),
            "max_frames": self.spin_max.value(),
            "max_size": self.spin_size.value(),
            "trim_start": self.spin_start.value(),
            "trim_end": self.spin_end.value(),
        }


class GifCanvas(QWidget):
    text_moved = pyqtSignal(float, float)
    text_clicked = pyqtSignal(int)
    frame_step = pyqtSignal(int)
    canvas_clicked = pyqtSignal(float, float)
    drag_ended = pyqtSignal()          # snapshot undo after drag
    size_changed = pyqtSignal(int)     # font size delta from drag-resize
    path_finished = pyqtSignal(list)   # four normalized Bezier points

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)

        self._base_pixmap: QPixmap | None = None
        self._prev_pixmap: QPixmap | None = None  # onion skin
        self._layers: list[TextLayer] = []
        self._selected_id = -1
        self._current_frame = 0
        self._total_frames = 1
        self._gif_rect = QRectF()
        self._dragging = False
        self._resizing = False
        self._resize_start_y = 0
        self._resize_start_size = 0
        self._did_drag = False
        self._hovering_id = -1
        self._rendered = QPixmap()
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._panning = False
        self._pan_start = QPointF()
        self._pan_offset_start = (0.0, 0.0)
        self._path_mode = False
        self._path_points = []
        self.onion_skin = False
        self.onion_opacity = 0.3

    def set_frame(self, pixmap, prev_pixmap, layers, frame, selected_id, total_frames):
        self._base_pixmap = pixmap
        self._prev_pixmap = prev_pixmap
        self._layers = layers
        self._current_frame = frame
        self._selected_id = selected_id
        self._total_frames = total_frames
        self._render()
        self.update()

    def begin_path_capture(self, points=None):
        self._path_mode = True
        self._path_points = _normalize_path_points(points)
        self._dragging = False
        self._resizing = False
        self._hovering_id = -1
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self._render()
        self.update()

    def cancel_path_capture(self):
        if not self._path_mode:
            return
        self._path_mode = False
        self._path_points = []
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self._render()
        self.update()

    def paintEvent(self, event):
        if self._rendered.isNull():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            bg = QLinearGradient(0, 0, 0, self.height())
            bg.setColorAt(0.0, QColor("#171c24"))
            bg.setColorAt(1.0, QColor("#0d1117"))
            p.fillRect(self.rect(), bg)

            stage = QRectF(
                self.width() * 0.12, self.height() * 0.15,
                self.width() * 0.76, self.height() * 0.7
            )
            p.setPen(QPen(QColor("#2a3446"), 1))
            p.setBrush(QColor("#171d27"))
            p.drawRoundedRect(stage, 22, 22)

            inner = stage.adjusted(24, 24, -24, -24)
            p.setPen(QPen(QColor("#344154"), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor("#121821"))
            p.drawRoundedRect(inner, 16, 16)

            p.setPen(QColor("#f7fafc"))
            p.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
            p.drawText(
                QRectF(inner.left(), inner.top() + inner.height() * 0.18, inner.width(), 34),
                Qt.AlignmentFlag.AlignHCenter,
                "Load a GIF or video"
            )

            p.setPen(QColor("#a0acbc"))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(
                QRectF(inner.left(), inner.top() + inner.height() * 0.34, inner.width(), 50),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap),
                "Drop a clip onto the stage or use Load Media to start tracking text across frames."
            )

            chip = QRectF(inner.center().x() - 108, inner.bottom() - 54, 216, 28)
            p.setPen(QPen(QColor("#39506f"), 1))
            p.setBrush(QColor("#10161f"))
            p.drawRoundedRect(chip, 14, 14)
            p.setPen(QColor("#76b0ff"))
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, "Drag and drop supported")
            p.end()
            return
        p = QPainter(self)
        p.drawPixmap(0, 0, self._rendered)
        p.end()

    def _render(self):
        if not self._base_pixmap:
            return
        cw, ch = self.width(), self.height()
        pw, ph = self._base_pixmap.width(), self._base_pixmap.height()
        base_scale = min(cw / pw, ch / ph, 3.0)
        scale = base_scale * self._zoom
        sw, sh = int(pw * scale), int(ph * scale)
        ox = int((cw - sw) / 2 + self._pan_x)
        oy = int((ch - sh) / 2 + self._pan_y)
        self._gif_rect = QRectF(ox, oy, sw, sh)

        result = QPixmap(cw, ch)
        result.fill(Qt.GlobalColor.transparent)
        p = QPainter(result)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        bg = QLinearGradient(0, 0, 0, ch)
        bg.setColorAt(0.0, QColor("#171c24"))
        bg.setColorAt(1.0, QColor("#0d1117"))
        p.fillRect(QRectF(0, 0, cw, ch), bg)

        stage_rect = QRectF(ox - 18, oy - 18, sw + 36, sh + 36)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(stage_rect.adjusted(0, 10, 0, 10), 24, 24)
        p.setBrush(QColor("#171d27"))
        p.setPen(QPen(QColor("#2a3446"), 1))
        p.drawRoundedRect(stage_rect, 24, 24)

        # Checkerboard
        cs = 12
        clip_r = QRectF(max(0, ox), max(0, oy), min(sw, cw - max(0, ox)), min(sh, ch - max(0, oy)))
        for cy in range(int(clip_r.top()), int(clip_r.bottom()), cs):
            for cx in range(int(clip_r.left()), int(clip_r.right()), cs):
                g = ((cx - ox) // cs + (cy - oy) // cs) % 2
                p.fillRect(cx, cy, cs, cs, QColor("#202733") if g else QColor("#171c24"))

        # Onion skin (previous frame)
        if self.onion_skin and self._prev_pixmap and self._current_frame > 0:
            p.setOpacity(self.onion_opacity)
            p.drawPixmap(ox, oy, sw, sh, self._prev_pixmap)
            p.setOpacity(1.0)
            # Tint overlay
            p.fillRect(QRectF(ox, oy, sw, sh), QColor(94, 162, 255, 28))

        # Current frame
        p.drawPixmap(ox, oy, sw, sh, self._base_pixmap)
        p.setPen(QPen(QColor("#313b4d"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self._gif_rect, 14, 14)

        # Text layers
        for layer in self._layers:
            if not layer.is_visible_at(self._current_frame, self._total_frames):
                continue
            kf = layer.get_interpolated(self._current_frame)
            sel = layer.id == self._selected_id
            hov = layer.id == self._hovering_id
            fade = layer.get_fade_opacity(self._current_frame, self._total_frames)
            self._draw_text_layer(p, layer, kf, ox, oy, sw, sh, scale, sel, hov, fade)

        selected_layer = next((l for l in self._layers if l.id == self._selected_id), None)
        if selected_layer and selected_layer.path_points:
            self._draw_path_overlay(p, selected_layer.path_points, ox, oy, sw, sh,
                                    selected_layer.accent, active=False)
        if self._path_mode:
            self._draw_path_overlay(p, self._path_points, ox, oy, sw, sh, "#f9e2af", active=True)

        # Zoom indicator
        if self._zoom != 1.0:
            badge = QRectF(12, ch - 34, 58, 24)
            p.setPen(QPen(QColor("#2f394a"), 1))
            p.setBrush(QColor("#10161f"))
            p.drawRoundedRect(badge, 12, 12)
            p.setPen(QColor("#c2d0e6"))
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"{self._zoom:.1f}x")

        p.end()
        self._rendered = result

    def _draw_path_overlay(self, p, points, ox, oy, sw, sh, color, active=False):
        points = _normalize_path_points(points)
        if not points:
            return

        screen_points = [QPointF(ox + x * sw, oy + y * sh) for x, y in points]
        accent = QColor(color)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if len(screen_points) >= 2:
            p.setOpacity(0.62 if active else 0.42)
            p.setPen(QPen(QColor("#d8dee9"), 1, Qt.PenStyle.DashLine))
            for i in range(len(screen_points) - 1):
                p.drawLine(screen_points[i], screen_points[i + 1])

        if len(screen_points) == 4:
            path = QPainterPath(screen_points[0])
            path.cubicTo(screen_points[1], screen_points[2], screen_points[3])
            p.setOpacity(0.95 if active else 0.72)
            p.setPen(QPen(accent, 3 if active else 2, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)

        p.setOpacity(1.0)
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        for idx, point in enumerate(screen_points):
            radius = 7 if active else 6
            p.setPen(QPen(QColor("#0d1117"), 2))
            p.setBrush(accent if idx in (0, len(screen_points) - 1) else QColor("#0d1117"))
            p.drawEllipse(point, radius, radius)
            p.setPen(QColor("#eef2f7") if idx not in (0, len(screen_points) - 1) else QColor("#0d1117"))
            label = str(idx + 1)
            p.drawText(QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2),
                       Qt.AlignmentFlag.AlignCenter, label)
        p.restore()

    def _draw_text_layer(self, p, layer, kf, ox, oy, sw, sh, scale, selected, hover, fade_mult):
        text = layer.text.upper() if layer.uppercase else layer.text
        text = apply_staggered_text(text, layer.stagger_mode, self._current_frame,
                                    layer.frame_in, layer.stagger_frames)
        if not text:
            return

        font = QFont(layer.font_family, max(4, int(kf.font_size * scale)))
        font.setBold(layer.bold)
        font.setItalic(layer.italic)
        tx = ox + kf.x * sw
        ty = oy + kf.y * sh

        p.save()
        p.translate(tx, ty)
        if kf.rotation != 0:
            p.rotate(kf.rotation)

        effective_opacity = kf.opacity * fade_mult
        p.setOpacity(effective_opacity)

        fm = QFontMetrics(font)
        lines = text.split('\n')
        total_h = fm.height() * len(lines)
        y_start = -total_h / 2
        max_w = max(fm.horizontalAdvance(l) for l in lines) if lines else 0
        bbox = QRectF(-max_w / 2 - 8, y_start - 8, max_w + 16, total_h + 16)

        # Background box (subtitle style)
        if layer.bg_box:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, int(160 * effective_opacity)))
            p.drawRoundedRect(bbox, 4, 4)

        # Selection indicator
        if selected or hover:
            p.setOpacity(1.0)
            accent = QColor(layer.accent)
            if selected:
                pen = QPen(accent, 2, Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(bbox, 4, 4)
                # Resize handle (bottom-right)
                hr = QPointF(bbox.right(), bbox.bottom())
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(accent)
                p.drawEllipse(hr, 5, 5)
                # Other corners
                for cx, cy in [(bbox.left(), bbox.top()), (bbox.right(), bbox.top()),
                                (bbox.left(), bbox.bottom())]:
                    p.drawEllipse(QPointF(cx, cy), 3, 3)
            elif hover:
                p.setPen(QPen(accent, 1, Qt.PenStyle.DotLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(bbox, 4, 4)
            p.setOpacity(effective_opacity)

        # Layer tag
        p.setOpacity(min(1.0, effective_opacity + (0.4 if selected else 0.16)))
        tag_font = QFont("Segoe UI", max(7, int(9 * scale)))
        tag_font.setBold(True)
        p.setFont(tag_font)
        tag_text = f" {layer.text.split(chr(10))[0][:12]} "
        tag_fm = QFontMetrics(tag_font)
        tag_w = tag_fm.horizontalAdvance(tag_text) + 8
        tag_rect = QRectF(bbox.left(), bbox.top() - tag_fm.height() - 2, tag_w, tag_fm.height() + 2)
        p.setPen(Qt.PenStyle.NoPen)
        abg = QColor(layer.accent)
        abg.setAlpha(230 if selected else 130)
        p.setBrush(abg)
        p.drawRoundedRect(tag_rect, 3, 3)
        p.setPen(QColor("#1e1e2e"))
        p.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag_text)
        p.setOpacity(effective_opacity)

        # Text rendering
        p.setFont(font)
        for i, line in enumerate(lines):
            bw = fm.horizontalAdvance(line)
            if layer.alignment == "center":
                lx = -bw / 2
            elif layer.alignment == "left":
                lx = -max_w / 2
            else:
                lx = max_w / 2 - bw
            ly = y_start + fm.height() * (i + 1) - fm.descent()

            path = QPainterPath()
            path.addText(lx, ly, font, line)

            ow = int(kf.outline_width * scale)
            if ow > 0:
                stroke_color = QColor(kf.outline_color)
                stroke_color.setAlpha(int(255 * kf.outline_opacity))
                p.setPen(QPen(stroke_color, ow, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)

            if layer.shadow:
                soff = max(2, int(2 * scale))
                sp = QPainterPath()
                sp.addText(lx + soff, ly + soff, font, line)
                p.setPen(Qt.PenStyle.NoPen)
                shadow_color = QColor(kf.shadow_color)
                shadow_color.setAlpha(int(255 * kf.shadow_opacity))
                p.setBrush(shadow_color)
                p.drawPath(sp)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(kf.color))
            p.drawPath(path)

        p.restore()

    # Mouse handling
    def _rel_pos(self, mx, my):
        if self._gif_rect.width() == 0:
            return None, None
        rx = (mx - self._gif_rect.x()) / self._gif_rect.width()
        ry = (my - self._gif_rect.y()) / self._gif_rect.height()
        return max(0, min(1, rx)), max(0, min(1, ry))

    def _find_layer_at(self, rx, ry):
        if rx is None:
            return None
        best, best_d = None, float('inf')
        sf = 1.0 / max(1, self._gif_rect.width())
        for layer in reversed(self._layers):
            if not layer.is_visible_at(self._current_frame, self._total_frames):
                continue
            d = layer.hit_test(rx, ry, self._current_frame, sf)
            if d is not None and d < best_d:
                best_d = d; best = layer
        return best

    def _check_resize_handle(self, mx, my):
        """Check if mouse is near bottom-right resize handle of selected layer."""
        if self._selected_id < 0 or self._gif_rect.width() == 0:
            return False
        for layer in self._layers:
            if layer.id != self._selected_id:
                continue
            kf = layer.get_interpolated(self._current_frame)
            scale = self._gif_rect.width() / max(1, self._base_pixmap.width()) if self._base_pixmap else 1
            font = QFont(layer.font_family, max(4, int(kf.font_size * scale)))
            font.setBold(layer.bold)
            fm = QFontMetrics(font)
            text = layer.text.upper() if layer.uppercase else layer.text
            lines = text.split('\n')
            max_w = max(fm.horizontalAdvance(l) for l in lines) if lines else 0
            total_h = fm.height() * len(lines)
            tx = self._gif_rect.x() + kf.x * self._gif_rect.width()
            ty = self._gif_rect.y() + kf.y * self._gif_rect.height()
            hx = tx + max_w / 2 + 8
            hy = ty + total_h / 2 + 8
            if abs(mx - hx) < 12 and abs(my - hy) < 12:
                return True
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self._pan_offset_start = (self._pan_x, self._pan_y)
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        mx, my = event.pos().x(), event.pos().y()
        if self._path_mode:
            rx, ry = self._rel_pos(mx, my)
            if rx is None:
                return
            self._path_points.append((rx, ry))
            if len(self._path_points) >= 4:
                points = list(self._path_points[:4])
                self._path_mode = False
                self._path_points = []
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                self.path_finished.emit(points)
            self._render()
            self.update()
            return
        # Check resize handle first
        if self._check_resize_handle(mx, my):
            self._resizing = True
            self._resize_start_y = my
            # Find current font size
            for layer in self._layers:
                if layer.id == self._selected_id:
                    kf = layer.get_interpolated(self._current_frame)
                    self._resize_start_size = kf.font_size
                    break
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
            return
        rx, ry = self._rel_pos(mx, my)
        if rx is None:
            return
        self._did_drag = False
        hit = self._find_layer_at(rx, ry)
        if hit:
            self.text_clicked.emit(hit.id)
            self._dragging = True
        else:
            self._dragging = True
            self.canvas_clicked.emit(rx, ry)

    def mouseMoveEvent(self, event):
        if self._panning:
            dx = event.position().x() - self._pan_start.x()
            dy = event.position().y() - self._pan_start.y()
            self._pan_x = self._pan_offset_start[0] + dx
            self._pan_y = self._pan_offset_start[1] + dy
            self._render()
            self.update()
            return
        if self._resizing:
            dy = event.pos().y() - self._resize_start_y
            new_size = max(8, min(200, self._resize_start_size + int(dy / 2)))
            self.size_changed.emit(new_size)
            return
        rx, ry = self._rel_pos(event.pos().x(), event.pos().y())
        if self._path_mode:
            if self.cursor().shape() != Qt.CursorShape.CrossCursor:
                self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            return
        if self._dragging and rx is not None:
            self._did_drag = True
            self.text_moved.emit(rx, ry)
        elif not self._dragging:
            # Hover: check resize handle vs text
            if self._check_resize_handle(event.pos().x(), event.pos().y()):
                if self.cursor().shape() != Qt.CursorShape.SizeFDiagCursor:
                    self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
                return
            hit = self._find_layer_at(rx, ry)
            new_hover = hit.id if hit else -1
            if new_hover != self._hovering_id:
                self._hovering_id = new_hover
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor if hit else Qt.CursorShape.ArrowCursor))
                self._render()
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        elif event.button() == Qt.MouseButton.LeftButton:
            if self._dragging and self._did_drag:
                self.drag_ended.emit()
            if self._resizing:
                self.drag_ended.emit()
            self._dragging = False
            self._resizing = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def wheelEvent(self, event):
        mods = event.modifiers()
        delta = event.angleDelta().y()
        if mods & Qt.KeyboardModifier.ControlModifier:
            # Zoom
            factor = 1.15 if delta > 0 else 1 / 1.15
            self._zoom = max(0.25, min(8.0, self._zoom * factor))
            self._render()
            self.update()
        else:
            # Frame step
            self.frame_step.emit(-1 if delta > 0 else 1)

    def reset_view(self):
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._render()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._base_pixmap:
            self._render()
            self.update()

    # Drag & drop GIF
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext == '.gif' or ext in VIDEO_EXTENSIONS:
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext == '.gif' or ext in VIDEO_EXTENSIONS:
                self.window()._load_gif_from_path(path)
                break


# ============================================================================
#  Timeline with Layer Bars
# ============================================================================

class LayerTimeline(QWidget):
    frame_clicked = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(80)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.total_frames = 1
        self.current_frame = 0
        self.layers: list[TextLayer] = []
        self.selected_id = -1

    def paintEvent(self, event):
        if self.total_frames <= 1:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        denom = max(1, self.total_frames - 1)
        margin_l, margin_r = 6, 6
        track_w = w - margin_l - margin_r

        # Background
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor("#151b24"))
        bg.setColorAt(1.0, QColor("#111720"))
        p.fillRect(0, 0, w, h, bg)

        # Frame ticks
        p.setPen(QColor("#202834"))
        tick_interval = max(1, self.total_frames // 20)
        for i in range(0, self.total_frames, tick_interval):
            x = margin_l + int(i / denom * track_w)
            p.drawLine(x, 0, x, h)

        # Layer bars
        bar_h = min(16, max(8, (h - 20) // max(1, len(self.layers))))
        bar_y = 4
        for layer in self.layers:
            fi = layer.frame_in
            fo = layer.frame_out if layer.frame_out >= 0 else self.total_frames - 1
            x1 = margin_l + int(fi / denom * track_w)
            x2 = margin_l + int(fo / denom * track_w)

            # Bar background
            color = QColor(layer.accent)
            color.setAlpha(110 if layer.id != self.selected_id else 205)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(x1, bar_y, max(4, x2 - x1), bar_h, 3, 3)

            # Keyframe diamonds
            for kf in layer.keyframes:
                kx = margin_l + int(kf.frame / denom * track_w)
                if x1 <= kx <= x2:
                    p.setBrush(QColor("#eef5ff") if layer.id == self.selected_id else QColor(layer.accent))
                    p.setPen(QPen(QColor("#111720"), 1))
                    diamond = QPainterPath()
                    dy = bar_y + bar_h / 2
                    diamond.moveTo(kx, dy - 4)
                    diamond.lineTo(kx + 4, dy)
                    diamond.lineTo(kx, dy + 4)
                    diamond.lineTo(kx - 4, dy)
                    diamond.closeSubpath()
                    p.drawPath(diamond)

            # Label
            if bar_h >= 10:
                p.setPen(QColor("#111720"))
                p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
                p.drawText(x1 + 4, bar_y + bar_h - 3, layer.text.split('\n')[0][:15])

            bar_y += bar_h + 2

        # Playhead
        cx = margin_l + int(self.current_frame / denom * track_w)
        p.setPen(QPen(QColor("#5ea2ff"), 2))
        p.drawLine(cx, 0, cx, h)
        # Playhead triangle
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#5ea2ff"))
        tri = QPainterPath()
        tri.moveTo(cx - 5, 0)
        tri.lineTo(cx + 5, 0)
        tri.lineTo(cx, 6)
        tri.closeSubpath()
        p.drawPath(tri)

        p.end()

    def mousePressEvent(self, event):
        if self.total_frames <= 1:
            return
        margin_l = 6
        track_w = self.width() - 12
        denom = max(1, self.total_frames - 1)
        frame = int((event.pos().x() - margin_l) / max(1, track_w) * denom + 0.5)
        self.frame_clicked.emit(max(0, min(self.total_frames - 1, frame)))


# ============================================================================
#  Layer List Widget
# ============================================================================

class LayerWidget(QFrame):
    selected = pyqtSignal(int)
    deleted = pyqtSignal(int)
    duplicated = pyqtSignal(int)
    visibility_changed = pyqtSignal(int, bool)

    def __init__(self, layer, is_selected):
        super().__init__()
        self.layer = layer
        self.setFixedHeight(48)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bc = layer.accent if is_selected else "#2a3446"
        bg = "#171d27" if is_selected else "#111720"
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: 1px solid {bc}; "
            f"border-radius: 12px; padding: 4px; }}"
        )
        lo = QHBoxLayout(self)
        lo.setContentsMargins(8, 4, 8, 4)
        lo.setSpacing(8)

        dot = QLabel()
        dot.setFixedSize(12, 12)
        dot.setStyleSheet(f"background-color: {layer.accent}; border-radius: 6px; border: none;")
        lo.addWidget(dot)

        vis_label = "●" if layer.visible else "○"
        vis = QPushButton(vis_label)
        vis.setObjectName("layerAction")
        vis.setFixedSize(30, 26)
        vis.setToolTip("Visible" if layer.visible else "Hidden")
        vis.clicked.connect(lambda: (
            setattr(layer, 'visible', not layer.visible),
            self.visibility_changed.emit(layer.id, layer.visible)
        ))
        lo.addWidget(vis)

        lbl = QLabel(layer.text.split('\n')[0][:16] or "---")
        lbl.setStyleSheet(
            f"color: #eef2f7; font-weight: {'700' if is_selected else '500'}; border: none;"
        )
        lo.addWidget(lbl, 1)

        dup = QPushButton("2x")
        dup.setObjectName("layerAction")
        dup.setFixedSize(32, 26)
        dup.setToolTip("Duplicate layer")
        dup.clicked.connect(lambda: self.duplicated.emit(layer.id))
        lo.addWidget(dup)

        dl = QPushButton("X")
        dl.setObjectName("layerAction")
        dl.setFixedSize(26, 26)
        dl.setToolTip("Delete layer")
        dl.setStyleSheet(
            "background: #311921; color: #ffcad8; border: 1px solid #6a3342; "
            "border-radius: 8px; font-weight: 700; padding: 0;"
        )
        dl.clicked.connect(lambda: self.deleted.emit(layer.id))
        lo.addWidget(dl)

    def mousePressEvent(self, event):
        self.selected.emit(self.layer.id)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        dup = menu.addAction("Duplicate Layer")
        action = menu.exec(event.globalPos())
        if action == dup:
            self.duplicated.emit(self.layer.id)


# ============================================================================
#  Main Window
# ============================================================================

class GifTextApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"GifText v{VERSION}")
        self.setMinimumSize(1100, 700)
        self.resize(1300, 820)
        self.setObjectName("appWindow")

        self.gif_frames: list[QPixmap] = []
        self.gif_pil_frames: list[Image.Image] = []
        self.frame_durations: list[int] = []
        self.current_frame = 0
        self.total_frames = 0
        self.gif_width = 0
        self.gif_height = 0
        self.gif_path = ""

        self.layers: list[TextLayer] = []
        self.selected_layer: TextLayer | None = None
        self.undo_mgr = UndoManager()
        self.path_capture_layer_id: int | None = None
        self.active_worker: CancelableWorker | None = None
        self.active_thread: QThread | None = None
        self.active_work_label = ""
        self.pending_project_payload = None
        self.pending_tracking_layer_id = None
        self.diagnostics = DiagnosticsRecorder()
        self.diagnostic_lines: list[str] = []
        self.copied_keyframe_range: list[tuple[int, dict]] = []
        self.custom_font_paths: dict[str, str] = {}

        self.playing = False
        self.play_speed = 1.0
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self._advance_frame)
        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.setSingleShot(True)
        self.snapshot_timer.timeout.connect(self._snapshot)

        self._recent_files: list[str] = []
        self._load_recent()

        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start(30000)

        self._build_ui()
        self._setup_accessibility()
        self._flush_diagnostic_panel()
        self._check_autosave_recovery()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        # Left panel
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(12)

        header = QFrame()
        header.setObjectName("workspaceHeader")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(16, 14, 16, 14)
        hl.setSpacing(10)

        brand = QVBoxLayout()
        brand.setSpacing(2)
        title = QLabel("GifText Studio")
        title.setObjectName("appTitle")
        brand.addWidget(title)
        subtitle = QLabel("Animated caption tracking for GIFs, tuned for fast meme workflows.")
        subtitle.setObjectName("appSubtitle")
        subtitle.setWordWrap(True)
        brand.addWidget(subtitle)
        hl.addLayout(brand)

        primary_row = QHBoxLayout()
        primary_row.setSpacing(8)

        self.btn_load = QPushButton("Load Media")
        self.btn_load.setObjectName("accent")
        self.btn_load.setMinimumHeight(36)
        self.btn_load.clicked.connect(self._load_gif)
        primary_row.addWidget(self.btn_load)

        self.btn_export = QPushButton("Export")
        self.btn_export.setObjectName("ghost")
        self.btn_export.setMinimumHeight(36)
        self.btn_export.clicked.connect(self._export_gif)
        self.btn_export.setEnabled(False)
        primary_row.addWidget(self.btn_export)

        self.btn_export_fit = QPushButton("Export ≤ MB")
        self.btn_export_fit.setObjectName("ghost")
        self.btn_export_fit.setMinimumHeight(36)
        self.btn_export_fit.clicked.connect(self._export_size_target)
        self.btn_export_fit.setEnabled(False)
        primary_row.addWidget(self.btn_export_fit)

        # Recent files dropdown
        self.btn_recent = QPushButton("Recent")
        self.btn_recent.setObjectName("ghost")
        self.btn_recent.setMinimumHeight(32)
        self.btn_recent.clicked.connect(self._show_recent_menu)
        primary_row.addWidget(self.btn_recent)

        primary_row.addStretch()

        self.info_label = QLabel("No clip loaded")
        self.info_label.setObjectName("workspaceMeta")
        primary_row.addWidget(self.info_label)
        hl.addLayout(primary_row)

        # Save/Load project
        utility_row = QHBoxLayout()
        utility_row.setSpacing(8)
        self.btn_save_proj = QPushButton("Save Project")
        self.btn_save_proj.setObjectName("ghost")
        self.btn_save_proj.setMinimumHeight(36)
        self.btn_save_proj.clicked.connect(self._save_project)
        self.btn_save_proj.setEnabled(False)
        utility_row.addWidget(self.btn_save_proj)

        self.btn_load_proj = QPushButton("Open Project")
        self.btn_load_proj.setObjectName("ghost")
        self.btn_load_proj.setMinimumHeight(36)
        self.btn_load_proj.clicked.connect(self._load_project)
        utility_row.addWidget(self.btn_load_proj)

        self.btn_import_subs = QPushButton("Import Subtitles")
        self.btn_import_subs.setObjectName("ghost")
        self.btn_import_subs.setMinimumHeight(36)
        self.btn_import_subs.clicked.connect(self._import_subtitles)
        self.btn_import_subs.setEnabled(False)
        utility_row.addWidget(self.btn_import_subs)

        self.btn_save_template = QPushButton("Save Template")
        self.btn_save_template.setObjectName("ghost")
        self.btn_save_template.setMinimumHeight(36)
        self.btn_save_template.clicked.connect(self._save_template)
        self.btn_save_template.setEnabled(False)
        utility_row.addWidget(self.btn_save_template)

        self.btn_load_template = QPushButton("Load Template")
        self.btn_load_template.setObjectName("ghost")
        self.btn_load_template.setMinimumHeight(36)
        self.btn_load_template.clicked.connect(self._load_template)
        self.btn_load_template.setEnabled(False)
        utility_row.addWidget(self.btn_load_template)

        # Undo/Redo
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setObjectName("ghost")
        self.btn_undo.setMinimumHeight(36)
        self.btn_undo.clicked.connect(self._undo)
        self.btn_undo.setEnabled(False)
        utility_row.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("Redo")
        self.btn_redo.setObjectName("ghost")
        self.btn_redo.setMinimumHeight(36)
        self.btn_redo.clicked.connect(self._redo)
        self.btn_redo.setEnabled(False)
        utility_row.addWidget(self.btn_redo)

        self.btn_cancel_work = QPushButton("Cancel Work")
        self.btn_cancel_work.setObjectName("danger")
        self.btn_cancel_work.setMinimumHeight(36)
        self.btn_cancel_work.clicked.connect(self._cancel_active_worker)
        self.btn_cancel_work.setVisible(False)
        self.btn_cancel_work.setEnabled(False)
        utility_row.addWidget(self.btn_cancel_work)

        utility_row.addStretch()

        self.hint_label = QLabel("Drop a GIF or video to begin, then add a text layer and scrub frame by frame.")
        self.hint_label.setObjectName("workspaceHint")
        utility_row.addWidget(self.hint_label)
        hl.addLayout(utility_row)

        # Canvas options row
        opts_wrap = QFrame()
        opts_wrap.setObjectName("commandBar")
        opts = QHBoxLayout(opts_wrap)
        opts.setContentsMargins(12, 10, 12, 10)
        opts.setSpacing(10)

        self.chk_onion = QCheckBox("Onion Skin")
        self.chk_onion.toggled.connect(self._toggle_onion)
        opts.addWidget(self.chk_onion)

        btn_reset_view = QPushButton("Reset View")
        btn_reset_view.setObjectName("ghost")
        btn_reset_view.setMinimumHeight(30)
        btn_reset_view.clicked.connect(lambda: self.canvas.reset_view())
        opts.addWidget(btn_reset_view)

        speed_label = QLabel("Preview speed")
        speed_label.setObjectName("sectionNote")
        opts.addWidget(speed_label)
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25x", "0.5x", "1x", "2x", "4x"])
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        self.speed_combo.setFixedWidth(70)
        opts.addWidget(self.speed_combo)

        self.btn_trim = QPushButton("Trim Frames")
        self.btn_trim.setObjectName("ghost")
        self.btn_trim.setMinimumHeight(30)
        self.btn_trim.clicked.connect(self._trim_frames)
        self.btn_trim.setEnabled(False)
        opts.addWidget(self.btn_trim)

        self.btn_resize = QPushButton("Resize")
        self.btn_resize.setObjectName("ghost")
        self.btn_resize.setMinimumHeight(30)
        self.btn_resize.clicked.connect(self._resize_source)
        self.btn_resize.setEnabled(False)
        opts.addWidget(self.btn_resize)

        opts.addStretch()
        hl.addWidget(opts_wrap)
        ll.addWidget(header)

        # Canvas
        canvas_shell = QFrame()
        canvas_shell.setObjectName("canvasShell")
        canvas_lo = QVBoxLayout(canvas_shell)
        canvas_lo.setContentsMargins(10, 10, 10, 10)
        canvas_lo.setSpacing(0)

        self.canvas = GifCanvas()
        self.canvas.text_moved.connect(self._on_text_moved)
        self.canvas.text_clicked.connect(self._select_layer)
        self.canvas.frame_step.connect(self._step_frame)
        self.canvas.canvas_clicked.connect(self._on_canvas_click)
        self.canvas.drag_ended.connect(self._snapshot)
        self.canvas.size_changed.connect(self._on_canvas_resize)
        self.canvas.path_finished.connect(self._finish_path_capture)
        canvas_lo.addWidget(self.canvas, 1)
        ll.addWidget(canvas_shell, 1)

        # Timeline
        timeline = QFrame()
        timeline.setObjectName("timeline")
        tl = QVBoxLayout(timeline)
        tl.setContentsMargins(10, 10, 10, 10)
        tl.setSpacing(8)

        self.layer_timeline = LayerTimeline()
        self.layer_timeline.frame_clicked.connect(self._set_frame)
        tl.addWidget(self.layer_timeline)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.btn_play = QPushButton("Play")
        self.btn_play.setObjectName("transport")
        self.btn_play.setFixedHeight(34)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_play.setEnabled(False)
        controls.addWidget(self.btn_play)

        self.btn_prev = QPushButton("<")
        self.btn_prev.setObjectName("transport")
        self.btn_prev.setFixedSize(42, 34)
        self.btn_prev.clicked.connect(lambda: self._step_frame(-1))
        self.btn_prev.setEnabled(False)
        controls.addWidget(self.btn_prev)

        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.valueChanged.connect(self._set_frame)
        controls.addWidget(self.frame_slider, 1)

        self.btn_next = QPushButton(">")
        self.btn_next.setObjectName("transport")
        self.btn_next.setFixedSize(42, 34)
        self.btn_next.clicked.connect(lambda: self._step_frame(1))
        self.btn_next.setEnabled(False)
        controls.addWidget(self.btn_next)

        self.frame_label = QLabel("0 / 0")
        self.frame_label.setObjectName("frameLabel")
        self.frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls.addWidget(self.frame_label)

        tl.addLayout(controls)
        ll.addWidget(timeline)
        splitter.addWidget(left)

        # Right panel
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setMinimumWidth(360)
        right_inner = QWidget()
        rl = QVBoxLayout(right_inner)
        rl.setContentsMargins(4, 0, 10, 0)
        rl.setSpacing(12)
        right_inner.setFixedWidth(360)

        panel_header = QFrame()
        panel_header.setObjectName("panelHeader")
        phl = QVBoxLayout(panel_header)
        phl.setContentsMargins(14, 12, 14, 12)
        phl.setSpacing(4)
        panel_title = QLabel("Inspector")
        panel_title.setObjectName("panelTitle")
        phl.addWidget(panel_title)
        panel_subtitle = QLabel("Follow the workflow from top to bottom to build, style, and animate each caption.")
        panel_subtitle.setObjectName("panelSubtitle")
        panel_subtitle.setWordWrap(True)
        phl.addWidget(panel_subtitle)

        self.selection_card = QFrame()
        self.selection_card.setObjectName("selectionCard")
        scl = QVBoxLayout(self.selection_card)
        scl.setContentsMargins(12, 12, 12, 12)
        scl.setSpacing(4)
        self.selection_eyebrow = QLabel("Current Selection")
        self.selection_eyebrow.setObjectName("selectionEyebrow")
        scl.addWidget(self.selection_eyebrow)
        self.selection_name = QLabel("No layer selected")
        self.selection_name.setObjectName("selectionTitle")
        scl.addWidget(self.selection_name)
        self.selection_meta = QLabel("Load a GIF, then add a text layer to start editing.")
        self.selection_meta.setObjectName("selectionMeta")
        self.selection_meta.setWordWrap(True)
        scl.addWidget(self.selection_meta)
        self.selection_state = QLabel("Nothing to edit yet")
        self.selection_state.setObjectName("selectionState")
        scl.addWidget(self.selection_state)
        phl.addWidget(self.selection_card)
        rl.addWidget(panel_header)

        # Layers
        lg = QGroupBox("1. Layers")
        ll2 = QVBoxLayout(lg)
        ll2.setSpacing(8)
        layers_note = QLabel("Start with one label per person or object, then duplicate for variations.")
        layers_note.setObjectName("sectionNote")
        layers_note.setWordWrap(True)
        ll2.addWidget(layers_note)
        self.btn_add = QPushButton("+ Add Text Layer")
        self.btn_add.setObjectName("accent")
        self.btn_add.setMinimumHeight(36)
        self.btn_add.clicked.connect(self._add_layer)
        self.btn_add.setEnabled(False)
        ll2.addWidget(self.btn_add)
        self.layers_list = QVBoxLayout()
        self.layers_list.setSpacing(6)
        ll2.addLayout(self.layers_list)
        rl.addWidget(lg)

        # Presets
        pg = QGroupBox("2. Looks")
        pgl = QVBoxLayout(pg)
        pgl.setSpacing(8)
        presets_note = QLabel("Pick a visual direction first, then refine the details below.")
        presets_note.setObjectName("sectionNote")
        presets_note.setWordWrap(True)
        pgl.addWidget(presets_note)
        pl = QGridLayout()
        pl.setHorizontalSpacing(6)
        pl.setVerticalSpacing(6)
        for idx, name in enumerate(MEME_PRESETS):
            btn = QPushButton(name)
            btn.setObjectName("preset")
            btn.clicked.connect(lambda checked, n=name: self._apply_preset(n))
            pl.addWidget(btn, idx // 2, idx % 2)
        pgl.addLayout(pl)
        rl.addWidget(pg)

        # Text Properties
        tg = QGroupBox("3. Content")
        tgl = QGridLayout(tg)
        tgl.setVerticalSpacing(4)
        tgl.setHorizontalSpacing(6)
        r = 0

        text_note = QLabel("Write the caption, choose the typeface, and decide how bold it should feel.")
        text_note.setObjectName("sectionNote")
        text_note.setWordWrap(True)
        tgl.addWidget(text_note, r, 0, 1, 3)
        r += 1

        tgl.addWidget(QLabel("Text:"), r, 0, Qt.AlignmentFlag.AlignTop)
        self.txt_input = QPlainTextEdit()
        self.txt_input.setPlaceholderText("Type meme text...\n(supports multiple lines)")
        self.txt_input.setMaximumHeight(84)
        self.txt_input.setTabChangesFocus(True)
        self.txt_input.textChanged.connect(self._on_text_changed)
        tgl.addWidget(self.txt_input, r, 1, 1, 2)
        r += 1

        tgl.addWidget(QLabel("Font:"), r, 0)
        font_row = QHBoxLayout()
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont("Impact"))
        self.font_combo.currentFontChanged.connect(self._on_font_changed)
        font_row.addWidget(self.font_combo, 1)
        self.btn_load_font = QPushButton("+")
        self.btn_load_font.setObjectName("ghost")
        self.btn_load_font.setFixedSize(30, 30)
        self.btn_load_font.setToolTip("Load a TTF/OTF font from disk")
        self.btn_load_font.clicked.connect(self._load_custom_font)
        font_row.addWidget(self.btn_load_font)
        tgl.addLayout(font_row, r, 1, 1, 2)
        r += 1

        style_row = QHBoxLayout()
        self.chk_bold = QCheckBox("Bold")
        self.chk_bold.setChecked(True)
        self.chk_bold.toggled.connect(self._on_style_changed)
        style_row.addWidget(self.chk_bold)
        self.chk_italic = QCheckBox("Italic")
        self.chk_italic.toggled.connect(self._on_style_changed)
        style_row.addWidget(self.chk_italic)
        self.chk_upper = QCheckBox("All Caps")
        self.chk_upper.setChecked(True)
        self.chk_upper.toggled.connect(self._on_style_changed)
        style_row.addWidget(self.chk_upper)
        self.chk_shadow = QCheckBox("Shadow")
        self.chk_shadow.toggled.connect(self._on_style_changed)
        style_row.addWidget(self.chk_shadow)
        self.chk_bgbox = QCheckBox("Background")
        self.chk_bgbox.toggled.connect(self._on_style_changed)
        style_row.addWidget(self.chk_bgbox)
        tgl.addLayout(style_row, r, 0, 1, 3)
        r += 1

        tgl.addWidget(QLabel("Align:"), r, 0)
        self.align_combo = QComboBox()
        self.align_combo.addItems(["center", "left", "right"])
        self.align_combo.currentTextChanged.connect(self._on_align_changed)
        tgl.addWidget(self.align_combo, r, 1, 1, 2)
        rl.addWidget(tg)

        # Animation
        ag = QGroupBox("4. Motion")
        agl = QGridLayout(ag)
        agl.setVerticalSpacing(4)
        agl.setHorizontalSpacing(6)
        ar = 0

        anim_note = QLabel("Use keyframes when the text needs to change size, opacity, rotation, or outline over time.")
        anim_note.setObjectName("sectionNote")
        anim_note.setWordWrap(True)
        agl.addWidget(anim_note, ar, 0, 1, 3)
        ar += 1

        agl.addWidget(QLabel("Font Size:"), ar, 0)
        self.spin_size = QSpinBox()
        self.spin_size.setRange(8, 200)
        self.spin_size.setValue(48)
        self.spin_size.valueChanged.connect(self._on_anim_prop_changed)
        agl.addWidget(self.spin_size, ar, 1, 1, 2)
        ar += 1

        agl.addWidget(QLabel("Opacity:"), ar, 0)
        self.spin_opacity = QDoubleSpinBox()
        self.spin_opacity.setRange(0.0, 1.0)
        self.spin_opacity.setSingleStep(0.05)
        self.spin_opacity.setValue(1.0)
        self.spin_opacity.valueChanged.connect(self._on_anim_prop_changed)
        agl.addWidget(self.spin_opacity, ar, 1, 1, 2)
        ar += 1

        agl.addWidget(QLabel("Rotation:"), ar, 0)
        self.spin_rotation = QDoubleSpinBox()
        self.spin_rotation.setRange(-360, 360)
        self.spin_rotation.setSingleStep(5)
        self.spin_rotation.valueChanged.connect(self._on_anim_prop_changed)
        agl.addWidget(self.spin_rotation, ar, 1, 1, 2)
        ar += 1

        agl.addWidget(QLabel("Curve:"), ar, 0)
        self.ease_combo = QComboBox()
        for easing_id, (label, _curve) in EASING_CURVES.items():
            self.ease_combo.addItem(label, easing_id)
        self.ease_combo.currentIndexChanged.connect(self._on_easing_changed)
        agl.addWidget(self.ease_combo, ar, 1, 1, 2)
        ar += 1

        agl.addWidget(QLabel("Outline:"), ar, 0)
        self.spin_outline = QSpinBox()
        self.spin_outline.setRange(0, 20)
        self.spin_outline.setValue(3)
        self.spin_outline.valueChanged.connect(self._on_anim_prop_changed)
        agl.addWidget(self.spin_outline, ar, 1, 1, 2)
        ar += 1

        agl.addWidget(QLabel("Stroke Alpha:"), ar, 0)
        self.spin_outline_opacity = QDoubleSpinBox()
        self.spin_outline_opacity.setRange(0.0, 1.0)
        self.spin_outline_opacity.setSingleStep(0.05)
        self.spin_outline_opacity.setValue(1.0)
        self.spin_outline_opacity.valueChanged.connect(self._on_anim_prop_changed)
        agl.addWidget(self.spin_outline_opacity, ar, 1, 1, 2)
        ar += 1

        agl.addWidget(QLabel("Shadow Alpha:"), ar, 0)
        self.spin_shadow_opacity = QDoubleSpinBox()
        self.spin_shadow_opacity.setRange(0.0, 1.0)
        self.spin_shadow_opacity.setSingleStep(0.05)
        self.spin_shadow_opacity.setValue(0.5)
        self.spin_shadow_opacity.valueChanged.connect(self._on_anim_prop_changed)
        agl.addWidget(self.spin_shadow_opacity, ar, 1, 1, 2)
        ar += 1

        color_row = QHBoxLayout()
        self.btn_color = QPushButton("Fill")
        self.btn_color.setFixedHeight(28)
        self.btn_color.clicked.connect(lambda: self._pick_color("text"))
        self.btn_color.setStyleSheet("background: #ffffff; color: #000; border-radius: 4px; font-weight: 600;")
        color_row.addWidget(self.btn_color)
        self.btn_outline_color = QPushButton("Stroke")
        self.btn_outline_color.setFixedHeight(28)
        self.btn_outline_color.clicked.connect(lambda: self._pick_color("outline"))
        self.btn_outline_color.setStyleSheet("background: #000000; color: #fff; border-radius: 4px; font-weight: 600;")
        color_row.addWidget(self.btn_outline_color)
        self.btn_shadow_color = QPushButton("Shadow")
        self.btn_shadow_color.setFixedHeight(28)
        self.btn_shadow_color.clicked.connect(lambda: self._pick_color("shadow"))
        self.btn_shadow_color.setStyleSheet("background: #000000; color: #fff; border-radius: 4px; font-weight: 600;")
        color_row.addWidget(self.btn_shadow_color)
        agl.addLayout(color_row, ar, 0, 1, 3)
        ar += 1

        self.pos_label = QLabel("Drag the label on the canvas to position it")
        self.pos_label.setStyleSheet("color: #585b70; font-size: 11px;")
        agl.addWidget(self.pos_label, ar, 0, 1, 3)
        ar += 1

        kf_row = QHBoxLayout()
        self.btn_set_kf = QPushButton("Add Keyframe")
        self.btn_set_kf.setObjectName("keyframeSet")
        self.btn_set_kf.setFixedHeight(30)
        self.btn_set_kf.clicked.connect(self._set_keyframe)
        kf_row.addWidget(self.btn_set_kf)
        self.btn_del_kf = QPushButton("Remove Keyframe")
        self.btn_del_kf.setObjectName("keyframeDel")
        self.btn_del_kf.setFixedHeight(30)
        self.btn_del_kf.clicked.connect(self._delete_keyframe)
        kf_row.addWidget(self.btn_del_kf)
        self.btn_copy_kf = QPushButton("Repeat 10 Frames")
        self.btn_copy_kf.setFixedHeight(30)
        self.btn_copy_kf.clicked.connect(self._repeat_keyframe_10_frames)
        kf_row.addWidget(self.btn_copy_kf)
        agl.addLayout(kf_row, ar, 0, 1, 3)
        ar += 1

        track_row = QHBoxLayout()
        self.btn_track_forward = QPushButton("Track Forward")
        self.btn_track_forward.setObjectName("keyframeSet")
        self.btn_track_forward.setFixedHeight(30)
        self.btn_track_forward.setToolTip("Generate keyframes from the selected layer position through the remaining frames")
        self.btn_track_forward.clicked.connect(self._track_selected_layer_forward)
        track_row.addWidget(self.btn_track_forward)
        agl.addLayout(track_row, ar, 0, 1, 3)
        ar += 1

        agl.addWidget(QLabel("Motion Span:"), ar, 0)
        self.spin_path_span = QSpinBox()
        self.spin_path_span.setRange(2, 9999)
        self.spin_path_span.setValue(30)
        self.spin_path_span.setSuffix(" frames")
        agl.addWidget(self.spin_path_span, ar, 1, 1, 2)
        ar += 1

        effect_row = QHBoxLayout()
        self.effect_buttons = []
        for name in ("Bounce", "Wiggle", "Shake"):
            btn = QPushButton(name)
            btn.setFixedHeight(30)
            btn.setObjectName("keyframeSet")
            btn.clicked.connect(lambda checked, n=name: self._apply_effect_preset(n))
            effect_row.addWidget(btn)
            self.effect_buttons.append(btn)
        agl.addLayout(effect_row, ar, 0, 1, 3)
        ar += 1

        path_row = QHBoxLayout()
        self.btn_draw_path = QPushButton("Draw Path")
        self.btn_draw_path.setObjectName("keyframeSet")
        self.btn_draw_path.setFixedHeight(30)
        self.btn_draw_path.setToolTip("Click four points on the canvas to generate Bezier path keyframes")
        self.btn_draw_path.clicked.connect(self._toggle_path_capture)
        path_row.addWidget(self.btn_draw_path)
        self.btn_clear_path = QPushButton("Clear Path")
        self.btn_clear_path.setObjectName("keyframeDel")
        self.btn_clear_path.setFixedHeight(30)
        self.btn_clear_path.clicked.connect(self._clear_path_guide)
        path_row.addWidget(self.btn_clear_path)
        agl.addLayout(path_row, ar, 0, 1, 3)
        ar += 1

        self.kf_info = QLabel("")
        self.kf_info.setStyleSheet("color: #f9e2af; font-size: 11px;")
        self.kf_info.setWordWrap(True)
        agl.addWidget(self.kf_info, ar, 0, 1, 3)
        rl.addWidget(ag)

        # Timing
        tmg = QGroupBox("5. Timing")
        tmgl = QGridLayout(tmg)
        tmgl.setVerticalSpacing(4)
        tr = 0

        timing_note = QLabel("Trim when the layer shows up and add fades so captions enter and leave cleanly.")
        timing_note.setObjectName("sectionNote")
        timing_note.setWordWrap(True)
        tmgl.addWidget(timing_note, tr, 0, 1, 2)
        tr += 1

        tmgl.addWidget(QLabel("Start Frame:"), tr, 0)
        self.spin_frame_in = QSpinBox()
        self.spin_frame_in.setRange(0, 9999)
        self.spin_frame_in.valueChanged.connect(self._on_timing_changed)
        tmgl.addWidget(self.spin_frame_in, tr, 1)
        tr += 1

        tmgl.addWidget(QLabel("End Frame:"), tr, 0)
        self.spin_frame_out = QSpinBox()
        self.spin_frame_out.setRange(-1, 9999)
        self.spin_frame_out.setSpecialValueText("Last")
        self.spin_frame_out.setValue(-1)
        self.spin_frame_out.valueChanged.connect(self._on_timing_changed)
        tmgl.addWidget(self.spin_frame_out, tr, 1)
        tr += 1

        tmgl.addWidget(QLabel("Fade In:"), tr, 0)
        self.spin_fade_in = QSpinBox()
        self.spin_fade_in.setRange(0, 100)
        self.spin_fade_in.setSuffix(" frames")
        self.spin_fade_in.valueChanged.connect(self._on_timing_changed)
        tmgl.addWidget(self.spin_fade_in, tr, 1)
        tr += 1

        tmgl.addWidget(QLabel("Fade Out:"), tr, 0)
        self.spin_fade_out = QSpinBox()
        self.spin_fade_out.setRange(0, 100)
        self.spin_fade_out.setSuffix(" frames")
        self.spin_fade_out.valueChanged.connect(self._on_timing_changed)
        tmgl.addWidget(self.spin_fade_out, tr, 1)
        tr += 1

        tmgl.addWidget(QLabel("Reveal:"), tr, 0)
        self.stagger_combo = QComboBox()
        self.stagger_combo.addItem("Off", "off")
        self.stagger_combo.addItem("Lines", "lines")
        self.stagger_combo.addItem("Words", "words")
        self.stagger_combo.addItem("Letters", "letters")
        self.stagger_combo.currentIndexChanged.connect(self._on_timing_changed)
        tmgl.addWidget(self.stagger_combo, tr, 1)
        tr += 1

        tmgl.addWidget(QLabel("Step:"), tr, 0)
        self.spin_stagger_frames = QSpinBox()
        self.spin_stagger_frames.setRange(1, 60)
        self.spin_stagger_frames.setSuffix(" frames")
        self.spin_stagger_frames.setValue(2)
        self.spin_stagger_frames.valueChanged.connect(self._on_timing_changed)
        tmgl.addWidget(self.spin_stagger_frames, tr, 1)
        rl.addWidget(tmg)

        range_group = QGroupBox("6. Range Tools")
        range_layout = QGridLayout(range_group)
        range_layout.setContentsMargins(10, 10, 10, 10)
        range_layout.setSpacing(8)
        range_layout.addWidget(QLabel("Start:"), 0, 0)
        self.spin_range_start = QSpinBox()
        self.spin_range_start.setRange(0, 9999)
        range_layout.addWidget(self.spin_range_start, 0, 1)
        range_layout.addWidget(QLabel("End:"), 1, 0)
        self.spin_range_end = QSpinBox()
        self.spin_range_end.setRange(0, 9999)
        range_layout.addWidget(self.spin_range_end, 1, 1)

        self.btn_apply_range = QPushButton("Apply Current")
        self.btn_apply_range.setObjectName("ghost")
        self.btn_apply_range.clicked.connect(self._apply_current_keyframe_to_range)
        range_layout.addWidget(self.btn_apply_range, 2, 0, 1, 2)

        self.btn_copy_range = QPushButton("Copy Keys")
        self.btn_copy_range.setObjectName("ghost")
        self.btn_copy_range.clicked.connect(self._copy_keyframes_in_range)
        range_layout.addWidget(self.btn_copy_range, 3, 0)

        self.btn_paste_range = QPushButton("Paste Keys")
        self.btn_paste_range.setObjectName("ghost")
        self.btn_paste_range.clicked.connect(self._paste_keyframe_range)
        range_layout.addWidget(self.btn_paste_range, 3, 1)

        self.btn_delete_range = QPushButton("Delete Keys")
        self.btn_delete_range.setObjectName("danger")
        self.btn_delete_range.clicked.connect(self._delete_keyframe_range)
        range_layout.addWidget(self.btn_delete_range, 4, 0)

        self.btn_visible_range = QPushButton("Set Visible")
        self.btn_visible_range.setObjectName("ghost")
        self.btn_visible_range.clicked.connect(self._set_visibility_to_range)
        range_layout.addWidget(self.btn_visible_range, 4, 1)
        rl.addWidget(range_group)

        delay_group = QGroupBox("7. Frame Delay")
        delay_layout = QGridLayout(delay_group)
        delay_layout.setVerticalSpacing(4)
        delay_note = QLabel("Override the delay for the current frame (in milliseconds).")
        delay_note.setObjectName("sectionNote")
        delay_note.setWordWrap(True)
        delay_layout.addWidget(delay_note, 0, 0, 1, 2)
        delay_layout.addWidget(QLabel("Delay (ms):"), 1, 0)
        self.spin_frame_delay = QSpinBox()
        self.spin_frame_delay.setRange(10, 10000)
        self.spin_frame_delay.setValue(100)
        self.spin_frame_delay.setSuffix(" ms")
        self.spin_frame_delay.valueChanged.connect(self._on_frame_delay_changed)
        delay_layout.addWidget(self.spin_frame_delay, 1, 1)
        self.btn_apply_delay_all = QPushButton("Apply to All Frames")
        self.btn_apply_delay_all.setObjectName("ghost")
        self.btn_apply_delay_all.clicked.connect(self._apply_delay_to_all)
        delay_layout.addWidget(self.btn_apply_delay_all, 2, 0, 1, 2)
        rl.addWidget(delay_group)

        diag_group = QGroupBox("Diagnostics")
        diag_layout = QVBoxLayout(diag_group)
        diag_layout.setContentsMargins(10, 10, 10, 10)
        diag_layout.setSpacing(8)
        self.diagnostics_view = QPlainTextEdit()
        self.diagnostics_view.setReadOnly(True)
        self.diagnostics_view.setMaximumBlockCount(80)
        self.diagnostics_view.setMaximumHeight(118)
        self.diagnostics_view.setPlaceholderText("No diagnostics yet")
        diag_layout.addWidget(self.diagnostics_view)
        self.btn_export_bundle = QPushButton("Export Diagnostics Bundle")
        self.btn_export_bundle.setObjectName("ghost")
        self.btn_export_bundle.setFixedHeight(28)
        self.btn_export_bundle.clicked.connect(self._export_diagnostics_bundle)
        diag_layout.addWidget(self.btn_export_bundle)
        rl.addWidget(diag_group)

        rl.addStretch()
        right_scroll.setWidget(right_inner)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([940, 360])

        self._set_layer_controls_enabled(False)
        self._refresh_chrome_state()
        self.statusBar().showMessage(f"GifText v{VERSION} - Load a GIF to get started")

    def _setup_accessibility(self):
        self.btn_load.setAccessibleName("Load media file")
        self.btn_load.setAccessibleDescription("Open a GIF or video file for editing")
        self.btn_export.setAccessibleName("Export")
        self.btn_export_fit.setAccessibleName("Export with size target")
        self.btn_export.setAccessibleDescription("Export the current project as GIF, WebP, or PNG sequence")
        self.btn_recent.setAccessibleName("Recent files")
        self.btn_save_proj.setAccessibleName("Save project")
        self.btn_load_proj.setAccessibleName("Open project")
        self.btn_import_subs.setAccessibleName("Import subtitles")
        self.btn_import_subs.setAccessibleDescription("Import SRT or VTT subtitle file as timed text layers")
        self.btn_save_template.setAccessibleName("Save layer setup as template")
        self.btn_load_template.setAccessibleName("Load template onto current GIF")
        self.btn_undo.setAccessibleName("Undo")
        self.btn_redo.setAccessibleName("Redo")
        self.btn_cancel_work.setAccessibleName("Cancel background work")
        self.btn_play.setAccessibleName("Play or pause animation")
        self.btn_prev.setAccessibleName("Previous frame")
        self.btn_next.setAccessibleName("Next frame")
        self.btn_add.setAccessibleName("Add text layer")
        self.frame_slider.setAccessibleName("Frame position")
        self.frame_slider.setAccessibleDescription("Scrub through animation frames")
        self.chk_onion.setAccessibleName("Onion skin overlay")
        self.speed_combo.setAccessibleName("Playback speed")
        self.txt_input.setAccessibleName("Caption text")
        self.font_combo.setAccessibleName("Font family")
        self.btn_load_font.setAccessibleName("Load custom font from disk")
        self.chk_bold.setAccessibleName("Bold text")
        self.chk_italic.setAccessibleName("Italic text")
        self.chk_upper.setAccessibleName("All caps")
        self.chk_shadow.setAccessibleName("Drop shadow")
        self.chk_bgbox.setAccessibleName("Background box")
        self.align_combo.setAccessibleName("Text alignment")
        self.spin_size.setAccessibleName("Font size")
        self.spin_opacity.setAccessibleName("Text opacity")
        self.spin_rotation.setAccessibleName("Rotation degrees")
        self.ease_combo.setAccessibleName("Easing curve")
        self.spin_outline.setAccessibleName("Outline width")
        self.spin_outline_opacity.setAccessibleName("Stroke opacity")
        self.spin_shadow_opacity.setAccessibleName("Shadow opacity")
        self.btn_color.setAccessibleName("Text fill color")
        self.btn_outline_color.setAccessibleName("Stroke color")
        self.btn_shadow_color.setAccessibleName("Shadow color")
        self.btn_set_kf.setAccessibleName("Add keyframe at current frame")
        self.btn_del_kf.setAccessibleName("Delete keyframe at current frame")
        self.btn_track_forward.setAccessibleName("Track forward with motion detection")
        self.btn_draw_path.setAccessibleName("Draw Bezier path")
        self.btn_clear_path.setAccessibleName("Clear path guide")
        self.spin_path_span.setAccessibleName("Path span in frames")
        self.stagger_combo.setAccessibleName("Stagger reveal mode")
        self.spin_stagger_frames.setAccessibleName("Stagger frame step")
        self.spin_frame_in.setAccessibleName("Layer start frame")
        self.spin_frame_out.setAccessibleName("Layer end frame")
        self.spin_fade_in.setAccessibleName("Fade in frames")
        self.spin_fade_out.setAccessibleName("Fade out frames")
        self.spin_frame_delay.setAccessibleName("Frame delay in milliseconds")
        self.btn_apply_delay_all.setAccessibleName("Apply current delay to all frames")
        self.btn_trim.setAccessibleName("Trim frame range")
        self.btn_resize.setAccessibleName("Resize source frames")
        self.diagnostics_view.setAccessibleName("Diagnostics log")
        self.btn_export_bundle.setAccessibleName("Export diagnostics bundle")
        self.canvas.setAccessibleName("Animation canvas")
        self.canvas.setAccessibleDescription("Preview and position text layers on the current frame")
        self.layer_timeline.setAccessibleName("Layer timeline")
        self.layer_timeline.setAccessibleDescription("Visual timeline showing layer bars and keyframe positions")
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.layer_timeline.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ================================================================
    #  Helpers
    # ================================================================

    def _record_diagnostic(self, level, action, message, path=None, exc=None):
        try:
            line = self.diagnostics.record(level, action, message, path, exc)
        except Exception as log_exc:
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            line = f"{timestamp} | ERROR | Diagnostics logging | {log_exc}"
        self.diagnostic_lines.append(line)
        if hasattr(self, "diagnostics_view"):
            self._flush_diagnostic_panel()
        return line

    def _flush_diagnostic_panel(self):
        if not hasattr(self, "diagnostics_view"):
            return
        self.diagnostics_view.setPlainText("\n\n".join(self.diagnostic_lines[-80:]))
        scrollbar = self.diagnostics_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _show_error(self, action, message, path=None, exc=None, dialog=True):
        self._record_diagnostic("error", action, message, path, exc)
        path_note = f" ({path})" if path else ""
        recovery = f"{action} failed{path_note}: {message}"
        self.statusBar().showMessage(recovery)
        if dialog and self.isVisible():
            QMessageBox.warning(self, f"{action} failed", recovery)

    def _export_diagnostics_bundle(self):
        bundle = build_diagnostics_bundle(
            version=VERSION,
            gif_path=self.gif_path,
            total_frames=self.total_frames,
            layer_count=len(self.layers),
            log_dir=str(self.diagnostics.log_dir),
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Diagnostics Bundle", "giftext-diagnostics.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if path:
            try:
                Path(path).write_text(bundle, encoding="utf-8")
                self.statusBar().showMessage(f"Diagnostics bundle saved to {os.path.basename(path)}")
            except Exception as exc:
                self._show_error("Save Bundle", str(exc), path=path, exc=exc)

    def _active_worker_path(self):
        worker = self.active_worker
        if worker is None:
            return None
        return getattr(worker, "path", None)

    def _reset_document_state(self):
        self.playing = False
        self.play_timer.stop()
        if hasattr(self, "btn_play"):
            self.btn_play.setText("Play")
        if self.snapshot_timer.isActive():
            self.snapshot_timer.stop()
        self.path_capture_layer_id = None
        if hasattr(self, "canvas"):
            self.canvas.cancel_path_capture()
        if hasattr(self, "btn_draw_path"):
            self.btn_draw_path.setText("Draw Path")
        self.layers = []
        self.selected_layer = None
        self.undo_mgr.clear()
        if hasattr(self, "info_label"):
            self._refresh_chrome_state()

    def _schedule_snapshot(self, delay_ms=280):
        self.snapshot_timer.start(delay_ms)

    def _ensure_keyframe(self, layer: TextLayer) -> TextKeyframe:
        kf = layer.get_keyframe_at(self.current_frame)
        if kf is None:
            kf = layer.get_interpolated(self.current_frame)
            kf.frame = self.current_frame
            layer.set_keyframe(kf)
        return kf

    def _resolve_export_target(self, path, selected_filter):
        ext = os.path.splitext(path)[1].lower()
        if ext in {".gif", ".webp", ".png", ".apng", ".mp4", ".webm"}:
            return path, ext

        filt = selected_filter.lower()
        if "apng" in filt:
            ext = ".apng"
        elif "webp" in filt:
            ext = ".webp"
        elif "png sequence" in filt or ("png" in filt and "apng" not in filt):
            ext = ".png"
        elif "mp4" in filt:
            ext = ".mp4"
        elif "webm" in filt:
            ext = ".webm"
        else:
            ext = ".gif"
        return path + ext, ext

    def _set_button_role(self, button, role):
        if button.objectName() == role:
            return
        button.setObjectName(role)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _refresh_chrome_state(self):
        has_gif = bool(self.gif_frames)
        self._set_button_role(self.btn_load, "ghost" if has_gif else "accent")
        self._set_button_role(self.btn_export, "accent" if has_gif else "ghost")
        if not has_gif:
            self.info_label.setText("No clip loaded")
            self.hint_label.setText("Drop a GIF or video to begin, then add a text layer and scrub frame by frame.")
        elif self.selected_layer:
            self.hint_label.setText("Drag to move, mouse wheel to scrub, Ctrl+wheel to zoom.")
        else:
            self.hint_label.setText("Add your first text layer, then track it across the timeline.")

    def _set_layer_controls_enabled(self, enabled):
        for widget in [
            self.txt_input, self.font_combo, self.chk_bold, self.chk_italic,
            self.chk_upper, self.chk_shadow, self.chk_bgbox, self.align_combo,
            self.spin_size, self.spin_opacity, self.spin_rotation, self.ease_combo, self.spin_outline,
            self.spin_outline_opacity, self.spin_shadow_opacity,
            self.btn_color, self.btn_outline_color, self.btn_shadow_color, self.btn_set_kf, self.btn_del_kf,
            self.btn_copy_kf, self.btn_track_forward, self.spin_path_span,
            self.btn_draw_path, self.btn_clear_path, self.spin_frame_in, self.spin_frame_out,
            self.spin_fade_in, self.spin_fade_out, self.stagger_combo, self.spin_stagger_frames,
            self.spin_range_start, self.spin_range_end, self.btn_apply_range, self.btn_copy_range,
            self.btn_paste_range, self.btn_delete_range, self.btn_visible_range,
        ] + self.effect_buttons:
            widget.setEnabled(enabled)

    def _start_worker(self, label, worker, finished_handler):
        if self.active_worker is not None:
            self.statusBar().showMessage(f"{self.active_work_label} already running")
            return False
        self.active_worker = worker
        self.active_work_label = label
        self.active_thread = QThread(self)
        worker.moveToThread(self.active_thread)
        self.active_thread.started.connect(worker.run)
        worker.progress.connect(self._on_worker_progress)
        worker.finished.connect(finished_handler)
        worker.failed.connect(self._on_worker_failed)
        worker.canceled.connect(self._on_worker_canceled)
        worker.finished.connect(lambda _result: self._finish_worker_thread())
        worker.failed.connect(lambda _message: self._finish_worker_thread())
        worker.canceled.connect(self._finish_worker_thread)
        self.btn_cancel_work.setVisible(True)
        self.btn_cancel_work.setEnabled(True)
        self.statusBar().showMessage(f"{label} started")
        self.active_thread.start()
        return True

    def _finish_worker_thread(self):
        thread = self.active_thread
        worker = self.active_worker
        self.active_worker = None
        self.active_thread = None
        self.active_work_label = ""
        self.btn_cancel_work.setEnabled(False)
        self.btn_cancel_work.setVisible(False)
        if thread is not None:
            thread.quit()
            thread.finished.connect(thread.deleteLater)
        if worker is not None:
            worker.deleteLater()

    def _cancel_active_worker(self):
        if self.active_worker is None:
            return
        self.active_worker.cancel()
        self.btn_cancel_work.setEnabled(False)
        self.statusBar().showMessage(f"Canceling {self.active_work_label}...")

    def _on_worker_progress(self, percent, message):
        self.statusBar().showMessage(f"{message} ({percent}%)")

    def _on_worker_failed(self, message):
        label = self.active_work_label or "Background work"
        path = self._active_worker_path()
        self.pending_project_payload = None
        self.pending_tracking_layer_id = None
        self._show_error(label, message, path=path)

    def _on_worker_canceled(self):
        label = self.active_work_label or "Background work"
        path = self._active_worker_path()
        self.pending_project_payload = None
        self.pending_tracking_layer_id = None
        self._record_diagnostic("warning", label, "Canceled by user", path=path)
        self.statusBar().showMessage(f"{self.active_work_label} canceled")

    # ================================================================
    #  GIF Loading
    # ================================================================

    def _load_gif(self):
        filters = "GIF Files (*.gif)"
        if HAS_IMAGEIO:
            filters = "Media Files (*.gif *.mp4 *.webm *.avi *.mov *.mkv *.m4v);;GIF Files (*.gif);;Video Files (*.mp4 *.webm *.avi *.mov *.mkv *.m4v);;All Files (*)"
        else:
            filters = "GIF Files (*.gif);;All Files (*)"
        path, _ = QFileDialog.getOpenFileName(self, "Open Media", "", filters)
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            self._load_video_from_path(path)
        else:
            self._load_gif_from_path(path)

    def _load_gif_from_path(self, path, project_payload=None):
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            self._load_video_from_path(path, project_payload=project_payload)
            return
        if self._start_worker("Load GIF", LoadGifWorker(path), self._on_gif_loaded):
            self.pending_project_payload = project_payload

    def _load_video_from_path(self, path, project_payload=None):
        meta = get_video_metadata(path)
        if meta is None:
            self._show_error("Load Video", "Could not read video metadata (imageio not available)", path=path, dialog=True)
            return
        if meta["duration"] <= 0:
            self._show_error("Load Video", "Could not determine video duration", path=path, dialog=True)
            return
        dlg = VideoImportDialog(self, path, meta)
        if dlg.exec() != QMessageBox.StandardButton.Ok:
            return
        settings = dlg.get_settings()
        worker = LoadVideoWorker(
            path,
            target_fps=settings["fps"],
            max_frames=settings["max_frames"],
            max_size=settings["max_size"],
            trim_start=settings["trim_start"],
            trim_end=settings["trim_end"],
        )
        if self._start_worker("Load Video", worker, self._on_gif_loaded):
            self.pending_project_payload = project_payload

    def _on_gif_loaded(self, data):
        try:
            project_payload = self.pending_project_payload
            if project_payload is not None:
                validate_project_payload(project_payload, total_frames=len(data["pil_frames"]))

            new_frames: list[QPixmap] = []
            new_pil: list[Image.Image] = []
            new_durations: list[int] = []
            new_width = data["width"]
            new_height = data["height"]
            expected_size = new_width * new_height * 4
            for idx, frame_bytes in enumerate(data["frame_bytes"]):
                if len(frame_bytes) != expected_size:
                    continue
                qimg = QImage(frame_bytes, new_width, new_height, QImage.Format.Format_RGBA8888)
                new_frames.append(QPixmap.fromImage(qimg.copy()))
                new_pil.append(data["pil_frames"][idx])
                new_durations.append(data["durations"][idx])
            if len(new_frames) < 2:
                self._show_error("Load GIF", "Not enough valid frames (need at least 2)", path=data.get("path"))
                self.pending_project_payload = None
                return

            self._reset_document_state()
            self.gif_frames = new_frames
            self.gif_pil_frames = new_pil
            self.frame_durations = new_durations
            self.gif_width = new_width
            self.gif_height = new_height
            self.gif_path = data["path"]
            self.total_frames = len(self.gif_frames)
            self.current_frame = 0
            self.frame_slider.blockSignals(True)
            self.frame_slider.setRange(0, self.total_frames - 1)
            self.frame_slider.setValue(0)
            self.frame_slider.blockSignals(False)
            self.frame_label.setText(f"1 / {self.total_frames}")
            self.btn_play.setEnabled(True)
            self.btn_prev.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_add.setEnabled(True)
            self.btn_export.setEnabled(True)
            self.btn_export_fit.setEnabled(True)
            self.btn_save_proj.setEnabled(True)
            self.btn_import_subs.setEnabled(True)
            self.btn_save_template.setEnabled(True)
            self.btn_load_template.setEnabled(True)
            self.btn_trim.setEnabled(True)
            self.btn_resize.setEnabled(True)
            self.layer_timeline.total_frames = self.total_frames
            self._rebuild_layer_list()
            self.info_label.setText(f"{self.gif_width}x{self.gif_height} | {self.total_frames}f | {os.path.basename(self.gif_path)}")
            self.hint_label.setText("Add a text layer, drag it on the stage, then step through frames.")
            self._refresh_chrome_state()

            self._add_recent(self.gif_path)
            self.pending_project_payload = None
            if project_payload is not None:
                TextLayer._counter = 0
                self.layers = [TextLayer.from_dict(d) for d in project_payload.get("layers", [])]
                self.selected_layer = self.layers[0] if self.layers else None
                self._rebuild_layer_list()

            self._snapshot()
            self._update_all()
            if project_payload is not None:
                self.statusBar().showMessage(f"Project loaded: {os.path.basename(project_payload.get('project_path', 'project'))}")
            else:
                self.statusBar().showMessage(f"Loaded {os.path.basename(self.gif_path)}")
        except Exception as e:
            self.pending_project_payload = None
            self._show_error("Apply GIF", str(e), path=data.get("path"), exc=e)

    # ================================================================
    #  Playback
    # ================================================================

    def _toggle_play(self):
        if self.playing:
            self.playing = False
            self.play_timer.stop()
            self.btn_play.setText("Play")
        else:
            self.playing = True
            self.btn_play.setText("Pause")
            self._advance_frame()

    def _advance_frame(self):
        if not self.playing or not self.gif_frames:
            return
        delay = int(self.frame_durations[self.current_frame] / self.play_speed)
        nxt = (self.current_frame + 1) % self.total_frames
        self.frame_slider.setValue(nxt)
        self.play_timer.start(max(10, delay))

    def _step_frame(self, delta):
        if self.gif_frames:
            self._set_frame(self.current_frame + delta)

    def _set_frame(self, frame):
        if not self.gif_frames:
            return
        self.current_frame = max(0, min(frame, self.total_frames - 1))
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(self.current_frame)
        self.frame_slider.blockSignals(False)
        self.frame_label.setText(f"{self.current_frame + 1} / {self.total_frames}")
        self._update_all()

    def _on_speed_changed(self, text):
        self.play_speed = float(text.replace('x', ''))

    def _update_all(self):
        if not self.gif_frames:
            return
        sel_id = self.selected_layer.id if self.selected_layer else -1
        prev_pm = self.gif_frames[self.current_frame - 1] if self.current_frame > 0 else None
        self.canvas.set_frame(
            self.gif_frames[self.current_frame], prev_pm,
            self.layers, self.current_frame, sel_id, self.total_frames
        )
        self.layer_timeline.layers = self.layers
        self.layer_timeline.current_frame = self.current_frame
        self.layer_timeline.selected_id = sel_id
        self.layer_timeline.total_frames = self.total_frames
        self.layer_timeline.update()
        self._refresh_chrome_state()
        self._sync_props_from_layer()
        self._update_undo_btns()
        if self.frame_durations and 0 <= self.current_frame < len(self.frame_durations):
            self.spin_frame_delay.blockSignals(True)
            self.spin_frame_delay.setValue(self.frame_durations[self.current_frame])
            self.spin_frame_delay.blockSignals(False)

    # ================================================================
    #  Layers
    # ================================================================

    def _add_layer(self):
        layer = TextLayer(f"Name {len(self.layers) + 1}")
        layer.keyframes = [TextKeyframe(frame=0, x=0.3 + 0.2 * (len(self.layers) % 3), y=0.3)]
        layer.frame_out = -1
        self.layers.append(layer)
        self.selected_layer = layer
        self._snapshot()
        self._rebuild_layer_list()
        self._update_all()
        self.txt_input.setFocus()
        self.txt_input.selectAll()
        self.statusBar().showMessage("Added layer - type a name and drag into position")

    def _duplicate_layer(self, layer_id):
        src = next((l for l in self.layers if l.id == layer_id), None)
        if not src:
            return
        layer = TextLayer(src.text + " copy")
        layer.font_family = src.font_family
        layer.bold = src.bold
        layer.italic = src.italic
        layer.alignment = src.alignment
        layer.shadow = src.shadow
        layer.uppercase = src.uppercase
        layer.bg_box = src.bg_box
        layer.frame_in = src.frame_in
        layer.frame_out = src.frame_out
        layer.fade_in = src.fade_in
        layer.fade_out = src.fade_out
        layer.path_points = list(src.path_points)
        layer.path_start_frame = src.path_start_frame
        layer.path_end_frame = src.path_end_frame
        layer.stagger_mode = src.stagger_mode
        layer.stagger_frames = src.stagger_frames
        layer.keyframes = [kf.copy() for kf in src.keyframes]
        # Offset position slightly
        for kf in layer.keyframes:
            kf.x = min(1.0, kf.x + 0.05)
            kf.y = min(1.0, kf.y + 0.05)
        if layer.path_points:
            layer.path_points = [
                (min(1.0, x + 0.05), min(1.0, y + 0.05))
                for x, y in layer.path_points
            ]
        self.layers.append(layer)
        self.selected_layer = layer
        self._snapshot()
        self._rebuild_layer_list()
        self._update_all()

    def _rebuild_layer_list(self):
        while self.layers_list.count():
            item = self.layers_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for layer in self.layers:
            sel = self.selected_layer and self.selected_layer.id == layer.id
            w = LayerWidget(layer, sel)
            w.selected.connect(self._select_layer)
            w.deleted.connect(self._delete_layer)
            w.duplicated.connect(self._duplicate_layer)
            w.visibility_changed.connect(self._on_layer_visibility_changed)
            self.layers_list.addWidget(w)

    def _on_layer_visibility_changed(self, _layer_id, _visible):
        self._snapshot()
        self._rebuild_layer_list()
        self._update_all()

    def _select_layer(self, layer_id):
        if self.path_capture_layer_id is not None and self.path_capture_layer_id != layer_id:
            self._cancel_path_capture()
        self.selected_layer = next((l for l in self.layers if l.id == layer_id), None)
        self._rebuild_layer_list()
        self._update_all()

    def _delete_layer(self, layer_id):
        name = next((l.text.split('\n')[0][:20] for l in self.layers if l.id == layer_id), "layer")
        self.layers = [l for l in self.layers if l.id != layer_id]
        if self.selected_layer and self.selected_layer.id == layer_id:
            self.selected_layer = self.layers[-1] if self.layers else None
        self._snapshot()
        self._rebuild_layer_list()
        self._update_all()
        self.statusBar().showMessage(f"Deleted \"{name}\" (Ctrl+Z to undo)")

    # ================================================================
    #  Canvas Interaction
    # ================================================================

    def _on_text_moved(self, rx, ry):
        if not self.selected_layer:
            return
        layer = self.selected_layer
        kf = self._ensure_keyframe(layer)
        kf.x = rx
        kf.y = ry
        self._update_all()

    def _on_canvas_click(self, rx, ry):
        if self.selected_layer:
            self._on_text_moved(rx, ry)

    def _on_canvas_resize(self, new_size):
        if not self.selected_layer:
            return
        layer = self.selected_layer
        kf = self._ensure_keyframe(layer)
        kf.font_size = new_size
        self._update_all()

    def _show_recent_menu(self):
        menu = QMenu(self)
        if not self._recent_files:
            menu.addAction("(no recent files)").setEnabled(False)
        else:
            for path in self._recent_files:
                if os.path.exists(path):
                    action = menu.addAction(os.path.basename(path))
                    action.setToolTip(path)
                    action.triggered.connect(lambda checked, p=path: self._load_gif_from_path(p))
        menu.exec(self.btn_recent.mapToGlobal(QPointF(0, self.btn_recent.height()).toPoint()))

    def _toggle_onion(self, checked):
        self.canvas.onion_skin = checked
        self._update_all()

    # ================================================================
    #  Properties Sync
    # ================================================================

    def _sync_props_from_layer(self):
        layer = self.selected_layer
        if not layer:
            if self.gif_frames:
                self.selection_name.setText("Choose or add a layer")
                self.selection_meta.setText("Use the Layers section to create a caption, then edit its content and motion here.")
                self.selection_state.setText(f"Frame {self.current_frame + 1} of {self.total_frames}")
            else:
                self.selection_name.setText("No layer selected")
                self.selection_meta.setText("Load a GIF, then add a text layer to start editing.")
                self.selection_state.setText("Nothing to edit yet")
            self._set_layer_controls_enabled(False)
            self._block(True)
            self.txt_input.setPlainText("")
            self.font_combo.setCurrentFont(QFont("Impact"))
            self.chk_bold.setChecked(True)
            self.chk_italic.setChecked(False)
            self.chk_upper.setChecked(True)
            self.chk_shadow.setChecked(False)
            self.chk_bgbox.setChecked(False)
            self.align_combo.setCurrentText("center")
            self.spin_size.setValue(48)
            self.spin_opacity.setValue(1.0)
            self.spin_rotation.setValue(0.0)
            self.ease_combo.setCurrentIndex(self.ease_combo.findData("ease_in_out"))
            self.spin_outline.setValue(3)
            self.spin_outline_opacity.setValue(1.0)
            self.spin_shadow_opacity.setValue(0.5)
            self.spin_frame_in.setValue(0)
            self.spin_frame_out.setValue(-1)
            self.spin_fade_in.setValue(0)
            self.spin_fade_out.setValue(0)
            self.stagger_combo.setCurrentIndex(self.stagger_combo.findData("off"))
            self.spin_stagger_frames.setValue(2)
            self.spin_path_span.setValue(30)
            self.spin_range_start.setValue(0)
            self.spin_range_end.setValue(0)
            self.btn_color.setStyleSheet(
                "background: #ffffff; color: #000; border-radius: 4px; font-weight: 600;"
            )
            self.btn_outline_color.setStyleSheet(
                "background: #000000; color: #fff; border-radius: 4px; font-weight: 600;"
            )
            self.btn_shadow_color.setStyleSheet(
                "background: #000000; color: #fff; border-radius: 4px; font-weight: 600;"
            )
            self._block(False)
            self.kf_info.setText("")
            self.pos_label.setText("No layer selected")
            return

        self._set_layer_controls_enabled(True)
        self._block(True)
        if self.txt_input.toPlainText() != layer.text:
            self.txt_input.setPlainText(layer.text)
        self.font_combo.setCurrentFont(QFont(layer.font_family))
        self.chk_bold.setChecked(layer.bold)
        self.chk_italic.setChecked(layer.italic)
        self.chk_upper.setChecked(layer.uppercase)
        self.chk_shadow.setChecked(layer.shadow)
        self.chk_bgbox.setChecked(layer.bg_box)
        self.align_combo.setCurrentText(layer.alignment)

        kf = layer.get_interpolated(self.current_frame)
        self.spin_size.setValue(kf.font_size)
        self.spin_opacity.setValue(kf.opacity)
        self.spin_rotation.setValue(kf.rotation)
        ease_idx = self.ease_combo.findData(kf.easing)
        self.ease_combo.setCurrentIndex(ease_idx if ease_idx >= 0 else self.ease_combo.findData("ease_in_out"))
        self.spin_outline.setValue(kf.outline_width)
        self.spin_outline_opacity.setValue(kf.outline_opacity)
        self.spin_shadow_opacity.setValue(kf.shadow_opacity)

        self.btn_color.setStyleSheet(
            f"background: {kf.color}; color: {'#000' if QColor(kf.color).lightness() > 128 else '#fff'}; "
            f"border-radius: 4px; font-weight: 600;"
        )
        self.btn_outline_color.setStyleSheet(
            f"background: {kf.outline_color}; color: {'#000' if QColor(kf.outline_color).lightness() > 128 else '#fff'}; "
            f"border-radius: 4px; font-weight: 600;"
        )
        self.btn_shadow_color.setStyleSheet(
            f"background: {kf.shadow_color}; color: {'#000' if QColor(kf.shadow_color).lightness() > 128 else '#fff'}; "
            f"border-radius: 4px; font-weight: 600;"
        )
        self.pos_label.setText(f"Position: ({kf.x:.2f}, {kf.y:.2f})")

        existing = layer.get_keyframe_at(self.current_frame)
        kf_frames = sorted(k.frame + 1 for k in layer.keyframes)
        marker = "[KEYFRAME]" if existing else "[interpolated]"
        path_text = ""
        if layer.path_points and layer.path_end_frame >= layer.path_start_frame:
            path_text = f" | Path: {layer.path_start_frame + 1}-{layer.path_end_frame + 1}"
            span = max(2, layer.path_end_frame - layer.path_start_frame + 1)
            self.spin_path_span.setValue(span)
        self.kf_info.setText(f"{marker}  KFs: {', '.join(map(str, kf_frames))}{path_text}")
        self.btn_clear_path.setEnabled(bool(layer.path_points))
        self.selection_name.setText(layer.text.split('\n')[0][:28] or f"Layer {layer.id}")
        self.selection_meta.setText(
            f"Frame {self.current_frame + 1} of {self.total_frames} | "
            f"{layer.font_family} | {layer.alignment.title()} aligned"
        )
        self.selection_state.setText(
            f"{'Keyframe locked' if existing else 'Interpolated preview'} | "
            f"{len(layer.keyframes)} keyframe{'s' if len(layer.keyframes) != 1 else ''}"
        )

        self.spin_frame_in.setValue(layer.frame_in)
        self.spin_frame_out.setValue(layer.frame_out)
        self.spin_fade_in.setValue(layer.fade_in)
        self.spin_fade_out.setValue(layer.fade_out)
        self.spin_range_start.setValue(layer.frame_in)
        self.spin_range_end.setValue(layer.frame_out if layer.frame_out >= 0 else max(0, self.total_frames - 1))
        stagger_idx = self.stagger_combo.findData(layer.stagger_mode)
        self.stagger_combo.setCurrentIndex(stagger_idx if stagger_idx >= 0 else self.stagger_combo.findData("off"))
        self.spin_stagger_frames.setValue(layer.stagger_frames)

        self._block(False)

    def _block(self, b):
        for w in [self.txt_input, self.spin_size, self.spin_opacity,
                  self.spin_rotation, self.spin_outline, self.font_combo,
                  self.spin_outline_opacity, self.spin_shadow_opacity,
                  self.ease_combo,
                  self.chk_bold, self.chk_italic, self.chk_upper, self.chk_shadow,
                  self.chk_bgbox, self.align_combo, self.spin_frame_in,
                  self.spin_frame_out, self.spin_fade_in, self.spin_fade_out,
                  self.stagger_combo, self.spin_stagger_frames, self.spin_path_span,
                  self.spin_range_start, self.spin_range_end]:
            w.blockSignals(b)

    def _on_text_changed(self):
        if not self.selected_layer:
            return
        self.selected_layer.text = self.txt_input.toPlainText()
        self._schedule_snapshot(420)
        self._rebuild_layer_list()
        self._update_all()

    def _load_custom_font(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Custom Font", "",
            "Font Files (*.ttf *.otf);;All Files (*)"
        )
        if not path:
            return
        from PyQt6.QtGui import QFontDatabase
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id < 0:
            self.statusBar().showMessage(f"Failed to load font: {os.path.basename(path)}")
            return
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            self.statusBar().showMessage(f"No font families found in {os.path.basename(path)}")
            return
        family = families[0]
        self.custom_font_paths[family.lower()] = path
        register_custom_font(family.lower(), path)
        self.font_combo.setCurrentFont(QFont(family))
        self.statusBar().showMessage(f"Loaded font: {family}")

    def _on_font_changed(self, font):
        if self.selected_layer:
            self.selected_layer.font_family = font.family()
            self._schedule_snapshot()
            self._update_all()

    def _on_style_changed(self):
        if not self.selected_layer:
            return
        self.selected_layer.bold = self.chk_bold.isChecked()
        self.selected_layer.italic = self.chk_italic.isChecked()
        self.selected_layer.uppercase = self.chk_upper.isChecked()
        self.selected_layer.shadow = self.chk_shadow.isChecked()
        self.selected_layer.bg_box = self.chk_bgbox.isChecked()
        self._schedule_snapshot()
        self._update_all()

    def _on_align_changed(self, a):
        if self.selected_layer:
            self.selected_layer.alignment = a
            self._schedule_snapshot()
            self._update_all()

    def _on_anim_prop_changed(self):
        if not self.selected_layer:
            return
        kf = self._ensure_keyframe(self.selected_layer)
        kf.font_size = self.spin_size.value()
        kf.opacity = self.spin_opacity.value()
        kf.rotation = self.spin_rotation.value()
        kf.outline_width = self.spin_outline.value()
        kf.outline_opacity = self.spin_outline_opacity.value()
        kf.shadow_opacity = self.spin_shadow_opacity.value()
        self._schedule_snapshot()
        self._update_all()

    def _on_easing_changed(self):
        if not self.selected_layer:
            return
        easing = self.ease_combo.currentData() or "ease_in_out"
        kf = self._ensure_keyframe(self.selected_layer)
        kf.easing = easing
        self._schedule_snapshot()
        self._update_all()

    def _on_timing_changed(self):
        if not self.selected_layer:
            return
        self.selected_layer.frame_in = self.spin_frame_in.value()
        self.selected_layer.frame_out = self.spin_frame_out.value()
        self.selected_layer.fade_in = self.spin_fade_in.value()
        self.selected_layer.fade_out = self.spin_fade_out.value()
        self.selected_layer.stagger_mode = self.stagger_combo.currentData() or "off"
        self.selected_layer.stagger_frames = self.spin_stagger_frames.value()
        self._schedule_snapshot()
        self._update_all()

    def _on_frame_delay_changed(self, value):
        if self.frame_durations and 0 <= self.current_frame < len(self.frame_durations):
            self.frame_durations[self.current_frame] = value

    def _apply_delay_to_all(self):
        if not self.frame_durations:
            return
        value = self.spin_frame_delay.value()
        self.frame_durations = [value] * len(self.frame_durations)
        self.statusBar().showMessage(f"All {len(self.frame_durations)} frames set to {value} ms")

    def _pick_color(self, target):
        if not self.selected_layer:
            return
        kf = self.selected_layer.get_interpolated(self.current_frame)
        if target == "text":
            initial = QColor(kf.color)
        elif target == "outline":
            initial = QColor(kf.outline_color)
        else:
            initial = QColor(kf.shadow_color)
        color = QColorDialog.getColor(initial, self, f"Pick {target} color")
        if not color.isValid():
            return
        layer = self.selected_layer
        existing = self._ensure_keyframe(layer)
        if target == "text":
            existing.color = color.name()
        elif target == "outline":
            existing.outline_color = color.name()
        else:
            existing.shadow_color = color.name()
        self._snapshot()
        self._update_all()

    def _apply_preset(self, name):
        if not self.selected_layer:
            return
        p = MEME_PRESETS[name]
        layer = self.selected_layer
        layer.font_family = p["font"]
        layer.bold = p["bold"]
        layer.uppercase = p["upper"]
        layer.shadow = p["shadow"]
        layer.bg_box = p["bg_box"]
        # Apply to current keyframe
        kf = self._ensure_keyframe(layer)
        kf.font_size = p["size"]
        kf.color = p["color"]
        kf.outline_color = p["outline_color"]
        kf.outline_width = p["outline_width"]
        kf.outline_opacity = 1.0
        kf.shadow_color = "#000000"
        kf.shadow_opacity = 0.5
        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(f"Applied preset: {name}")

    # ================================================================
    #  Keyframes
    # ================================================================

    def _set_keyframe(self):
        if not self.selected_layer:
            return
        layer = self.selected_layer
        kf = layer.get_keyframe_at(self.current_frame) or layer.get_interpolated(self.current_frame)
        kf.frame = self.current_frame
        kf.font_size = self.spin_size.value()
        kf.opacity = self.spin_opacity.value()
        kf.rotation = self.spin_rotation.value()
        kf.outline_width = self.spin_outline.value()
        kf.outline_opacity = self.spin_outline_opacity.value()
        kf.shadow_opacity = self.spin_shadow_opacity.value()
        kf.easing = self.ease_combo.currentData() or "ease_in_out"
        layer.set_keyframe(kf)
        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(f"Keyframe set at frame {self.current_frame + 1}")

    def _delete_keyframe(self):
        if not self.selected_layer:
            return
        if self.selected_layer.get_keyframe_at(self.current_frame):
            self.selected_layer.remove_keyframe(self.current_frame)
            self._snapshot()
            self._update_all()
            self.statusBar().showMessage(f"Keyframe deleted at frame {self.current_frame + 1}")

    def _range_bounds(self):
        start = min(self.spin_range_start.value(), self.spin_range_end.value())
        end = max(self.spin_range_start.value(), self.spin_range_end.value())
        if self.total_frames > 0:
            start = max(0, min(start, self.total_frames - 1))
            end = max(0, min(end, self.total_frames - 1))
        return start, end

    def _apply_current_keyframe_to_range(self):
        if not self.selected_layer:
            return
        start, end = self._range_bounds()
        source = self.selected_layer.get_keyframe_at(self.current_frame) or self.selected_layer.get_interpolated(self.current_frame)
        for frame in range(start, end + 1):
            kf = source.copy()
            kf.frame = frame
            self.selected_layer.set_keyframe(kf)
        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(f"Applied current keyframe to frames {start + 1}-{end + 1}")

    def _copy_keyframes_in_range(self):
        if not self.selected_layer:
            return
        start, end = self._range_bounds()
        copied = []
        for keyframe in sorted(self.selected_layer.keyframes, key=lambda k: k.frame):
            if start <= keyframe.frame <= end:
                copied.append((keyframe.frame - start, keyframe.to_dict()))
        self.copied_keyframe_range = copied
        self.statusBar().showMessage(f"Copied {len(copied)} keyframes from frames {start + 1}-{end + 1}")

    def _paste_keyframe_range(self):
        if not self.selected_layer:
            return
        if not self.copied_keyframe_range:
            self.statusBar().showMessage("No copied range keyframes to paste")
            return
        start, _end = self._range_bounds()
        pasted = 0
        max_frame = max(0, self.total_frames - 1)
        for offset, payload in self.copied_keyframe_range:
            frame = min(max_frame, start + offset)
            kf = TextKeyframe.from_dict(payload)
            kf.frame = frame
            self.selected_layer.set_keyframe(kf)
            pasted += 1
        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(f"Pasted {pasted} keyframes starting at frame {start + 1}")

    def _delete_keyframe_range(self):
        if not self.selected_layer:
            return
        start, end = self._range_bounds()
        before = len(self.selected_layer.keyframes)
        self.selected_layer.keyframes = [
            keyframe for keyframe in self.selected_layer.keyframes
            if not (start <= keyframe.frame <= end)
        ]
        if not self.selected_layer.keyframes:
            fallback = self.selected_layer.get_interpolated(start)
            fallback.frame = start
            self.selected_layer.keyframes = [fallback]
        removed = before - len(self.selected_layer.keyframes)
        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(f"Deleted {removed} keyframes from frames {start + 1}-{end + 1}")

    def _set_visibility_to_range(self):
        if not self.selected_layer:
            return
        start, end = self._range_bounds()
        self.selected_layer.frame_in = start
        self.selected_layer.frame_out = end
        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(f"Layer visible on frames {start + 1}-{end + 1}")

    def _repeat_keyframe_10_frames(self):
        if not self.selected_layer:
            return
        layer = self.selected_layer
        kf = layer.get_keyframe_at(self.current_frame)
        if not kf:
            kf = layer.get_interpolated(self.current_frame)

        # Copy to next 10 frames (or remaining)
        count = 0
        for f in range(self.current_frame, min(self.current_frame + 10, self.total_frames)):
            new_kf = kf.copy()
            new_kf.frame = f
            layer.set_keyframe(new_kf)
            count += 1

        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(
            f"Copied keyframe to {count} frames ({self.current_frame + 1}-{min(self.current_frame + 10, self.total_frames)})"
        )

    def _apply_effect_preset(self, name):
        if not self.selected_layer or not self.gif_frames:
            return
        if self.current_frame >= self.total_frames - 1:
            self.statusBar().showMessage(f"{name} needs at least one later frame")
            return

        frame_count = min(self.spin_path_span.value(), self.total_frames - self.current_frame)
        if frame_count < 2:
            self.statusBar().showMessage(f"{name} needs at least two frames")
            return

        for kf in build_effect_keyframes(self.selected_layer, name, self.current_frame, frame_count):
            self.selected_layer.set_keyframe(kf)

        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(
            f"{name} generated {frame_count} editable keyframes through frame {self.current_frame + frame_count}"
        )

    def _toggle_path_capture(self):
        if self.path_capture_layer_id is not None:
            self._cancel_path_capture()
            self.statusBar().showMessage("Path drawing cancelled")
            return
        if not self.selected_layer or not self.gif_frames:
            return
        if self.current_frame >= self.total_frames - 1:
            self.statusBar().showMessage("Path animation needs at least one later frame")
            return

        self.path_capture_layer_id = self.selected_layer.id
        self.btn_draw_path.setText("Cancel Path")
        self.canvas.begin_path_capture()
        self.statusBar().showMessage("Path mode: click start, control 1, control 2, end")

    def _cancel_path_capture(self):
        self.path_capture_layer_id = None
        self.btn_draw_path.setText("Draw Path")
        self.canvas.cancel_path_capture()

    def _finish_path_capture(self, points):
        layer = next((l for l in self.layers if l.id == self.path_capture_layer_id), None)
        self.path_capture_layer_id = None
        self.btn_draw_path.setText("Draw Path")
        points = _normalize_path_points(points)
        if not layer or len(points) != 4:
            self.canvas.cancel_path_capture()
            self.statusBar().showMessage("Path drawing did not produce four valid points")
            return

        frame_count = min(self.spin_path_span.value(), self.total_frames - self.current_frame)
        if frame_count < 2:
            self.statusBar().showMessage("Path animation needs at least two frames")
            return

        layer.path_points = points
        layer.path_start_frame = self.current_frame
        layer.path_end_frame = self.current_frame + frame_count - 1
        for kf in build_path_keyframes(layer, points, self.current_frame, frame_count):
            layer.set_keyframe(kf)

        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(
            f"Path generated {frame_count} keyframes through frame {layer.path_end_frame + 1}"
        )

    def _clear_path_guide(self):
        if self.path_capture_layer_id is not None:
            self._cancel_path_capture()
        if not self.selected_layer or not self.selected_layer.path_points:
            return
        self.selected_layer.path_points = []
        self.selected_layer.path_start_frame = 0
        self.selected_layer.path_end_frame = -1
        self._snapshot()
        self._update_all()
        self.statusBar().showMessage("Path guide cleared; generated keyframes remain editable")

    def _track_selected_layer_forward(self):
        if not self.selected_layer or not self.gif_pil_frames:
            return
        if self.current_frame >= self.total_frames - 1:
            self.statusBar().showMessage("Tracking needs at least one later frame")
            return

        layer = self.selected_layer
        seed = self._ensure_keyframe(layer)
        self.pending_tracking_layer_id = layer.id
        self._start_worker(
            "Track Forward",
            TrackingWorker(self.gif_pil_frames, self.current_frame, seed.x, seed.y),
            self._on_tracking_finished,
        )

    def _on_tracking_finished(self, positions):
        layer = next((l for l in self.layers if l.id == self.pending_tracking_layer_id), None)
        self.pending_tracking_layer_id = None
        if layer is None:
            self.statusBar().showMessage("Tracking finished but the layer no longer exists")
            return
        if len(positions) < 2:
            self.statusBar().showMessage("Tracking lost the point before a new keyframe could be made")
            return

        for frame_idx, x, y in positions:
            kf = layer.get_interpolated(frame_idx)
            kf.frame = frame_idx
            kf.x = x
            kf.y = y
            layer.set_keyframe(kf)

        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(
            f"Tracked {len(positions) - 1} frames and generated keyframes through frame {positions[-1][0] + 1}"
        )

    # ================================================================
    #  Undo / Redo
    # ================================================================

    def _snapshot(self):
        if self.snapshot_timer.isActive():
            self.snapshot_timer.stop()
        self.undo_mgr.snapshot(self.layers)
        self._update_undo_btns()

    def _restore_layers(self, result, label):
        prev_id = self.selected_layer.id if self.selected_layer else -1
        self.layers = result
        self.selected_layer = next((l for l in self.layers if l.id == prev_id), None)
        if self.selected_layer is None and self.layers:
            self.selected_layer = self.layers[-1]
        self._rebuild_layer_list()
        self._update_all()
        self.statusBar().showMessage(label)

    def _undo(self):
        if self.snapshot_timer.isActive():
            self._snapshot()
        result = self.undo_mgr.undo()
        if result is not None:
            self._restore_layers(result, "Undo")

    def _redo(self):
        if self.snapshot_timer.isActive():
            self._snapshot()
        result = self.undo_mgr.redo()
        if result is not None:
            self._restore_layers(result, "Redo")

    def _update_undo_btns(self):
        self.btn_undo.setEnabled(self.undo_mgr.can_undo)
        self.btn_redo.setEnabled(self.undo_mgr.can_redo)

    def keyPressEvent(self, event):
        # Ctrl+Z / Ctrl+Y
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Z:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._redo()
                else:
                    self._undo()
                return
            elif event.key() == Qt.Key.Key_Y:
                self._redo()
                return
            elif event.key() == Qt.Key.Key_S:
                self._save_project()
                return
        super().keyPressEvent(event)

    # ================================================================
    #  Project Save / Load
    # ================================================================

    def _import_subtitles(self):
        if not self.gif_pil_frames:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Subtitles", "", "Subtitle Files (*.srt *.vtt);;All Files (*)"
        )
        if path:
            self._import_subtitle_file(path)

    def _import_subtitle_file(self, path):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                entries = parse_subtitle_text(handle.read())
            if not entries:
                self._show_error("Import subtitles", "No subtitle cues found", path=path, dialog=False)
                return
            imported = subtitle_entries_to_layers(entries, self.frame_durations, self.total_frames)
            if not imported:
                self._show_error("Import subtitles", "No subtitle layers could be created", path=path, dialog=False)
                return
            self.layers.extend(imported)
            self.selected_layer = imported[0]
            self._rebuild_layer_list()
            self._snapshot()
            self._update_all()
            self.statusBar().showMessage(f"Imported {len(imported)} subtitle layers from {os.path.basename(path)}")
        except Exception as e:
            self._show_error("Import subtitles", str(e), path=path, exc=e)

    def _autosave_path(self):
        return Path.home() / ".giftext" / "autosave.giftext"

    def _autosave(self):
        if not self.gif_path or not self.layers:
            return
        try:
            path = self._autosave_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            project = build_project_payload(self.gif_path, self.layers, str(path))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(project, f, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            pass

    def _check_autosave_recovery(self):
        path = self._autosave_path()
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                project = json.load(f)
            gif_path = project.get("gif_path", "")
            if gif_path and os.path.isfile(gif_path) and project.get("layers"):
                reply = QMessageBox.question(
                    self, "Recover Session",
                    f"A previous session was found.\nSource: {os.path.basename(gif_path)}\n\nRecover it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    project["project_path"] = str(path)
                    self._load_gif_from_path(gif_path, project)
                    return
            path.unlink(missing_ok=True)
        except Exception:
            path.unlink(missing_ok=True)

    def _clear_autosave(self):
        try:
            self._autosave_path().unlink(missing_ok=True)
        except Exception:
            pass

    def _save_project(self):
        if not self.gif_path:
            return
        default = os.path.splitext(self.gif_path)[0] + ".giftext"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", default, "GifText Project (*.giftext)"
        )
        if not path:
            return
        project = build_project_payload(self.gif_path, self.layers, path)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(project, f, indent=2, ensure_ascii=False)
            self._clear_autosave()
            self.statusBar().showMessage(f"Project saved: {os.path.basename(path)}")
        except Exception as e:
            self._show_error("Save project", str(e), path=path, exc=e)

    def _save_template(self):
        if not self.layers:
            self.statusBar().showMessage("No layers to save as template")
            return
        template_dir = Path.home() / ".giftext" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Template", str(template_dir / "my_template.giftemplate"),
            "GifText Template (*.giftemplate)"
        )
        if not path:
            return
        template = {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "version": VERSION,
            "type": "template",
            "layers": [layer.to_dict() for layer in self.layers],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=2, ensure_ascii=False)
            self.statusBar().showMessage(f"Template saved: {os.path.basename(path)}")
        except Exception as e:
            self._show_error("Save template", str(e), path=path, exc=e)

    def _load_template(self):
        if not self.gif_pil_frames:
            self.statusBar().showMessage("Load a GIF first, then apply a template")
            return
        template_dir = Path.home() / ".giftext" / "templates"
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Template", str(template_dir),
            "GifText Template (*.giftemplate);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                template = json.load(f)
            layers_data = template.get("layers", [])
            if not isinstance(layers_data, list) or not layers_data:
                self._show_error("Load template", "Template contains no layers", path=path)
                return
            new_layers = [TextLayer.from_dict(d) for d in layers_data]
            self.layers = new_layers
            self.selected_layer = self.layers[0] if self.layers else None
            self._rebuild_layer_list()
            self._snapshot()
            self._update_all()
            self.statusBar().showMessage(f"Template applied: {os.path.basename(path)} ({len(new_layers)} layers)")
        except Exception as e:
            self._show_error("Load template", str(e), path=path, exc=e)

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Project", "", "GifText Project (*.giftext);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                project = json.load(f)
            validate_project_payload(project)
            gif_path = project.get("gif_path", "")
            rel_path = project.get("gif_relpath")
            candidates = []
            if rel_path:
                candidates.append(os.path.normpath(os.path.join(os.path.dirname(path), rel_path)))
            if gif_path:
                candidates.append(gif_path)
                candidates.append(os.path.join(os.path.dirname(path), os.path.basename(gif_path)))
            gif_path = next((candidate for candidate in candidates if candidate and os.path.exists(candidate)), "")
            if not gif_path:
                self._show_error("Load project", "GIF not found for this project file", path=path, dialog=False)
                return

            project["project_path"] = path
            self._load_gif_from_path(gif_path, project)
        except Exception as e:
            self._show_error("Load project", str(e), path=path, exc=e)

    # ================================================================
    #  Recent Files
    # ================================================================

    def _recent_path(self):
        return os.path.join(os.path.expanduser("~"), ".giftext_recent.json")

    def _load_recent(self):
        try:
            recent_path = self._recent_path()
            if not os.path.exists(recent_path):
                self._recent_files = []
                return
            with open(recent_path, encoding='utf-8') as f:
                data = json.load(f)
            self._recent_files = [p for p in data if isinstance(p, str)][:10] if isinstance(data, list) else []
        except Exception as e:
            self._recent_files = []
            self._record_diagnostic("error", "Load recent files", str(e), path=self._recent_path(), exc=e)

    def _add_recent(self, path):
        path = os.path.abspath(path)
        self._recent_files = [p for p in self._recent_files if p != path]
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:10]
        try:
            with open(self._recent_path(), 'w', encoding='utf-8') as f:
                json.dump(self._recent_files, f, ensure_ascii=False)
        except Exception as e:
            self._record_diagnostic("error", "Save recent files", str(e), path=self._recent_path(), exc=e)
            self.statusBar().showMessage(f"Recent files could not be saved: {e}")

    # ================================================================
    #  Export
    # ================================================================

    def _trim_frames(self):
        if self.total_frames < 3:
            self.statusBar().showMessage("Need at least 3 frames to trim")
            return
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Trim Frames")
        layout = QGridLayout(dlg)
        layout.addWidget(QLabel("Start frame:"), 0, 0)
        spin_start = QSpinBox()
        spin_start.setRange(0, self.total_frames - 2)
        spin_start.setValue(0)
        layout.addWidget(spin_start, 0, 1)
        layout.addWidget(QLabel("End frame:"), 1, 0)
        spin_end = QSpinBox()
        spin_end.setRange(1, self.total_frames - 1)
        spin_end.setValue(self.total_frames - 1)
        layout.addWidget(spin_end, 1, 1)
        layout.addWidget(QLabel(f"Total: {self.total_frames} frames"), 2, 0, 1, 2)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons, 3, 0, 1, 2)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        start = spin_start.value()
        end = spin_end.value()
        if start >= end or (start == 0 and end == self.total_frames - 1):
            return
        self.gif_frames = self.gif_frames[start:end + 1]
        self.gif_pil_frames = self.gif_pil_frames[start:end + 1]
        self.frame_durations = self.frame_durations[start:end + 1]
        self.total_frames = len(self.gif_frames)
        self.current_frame = 0
        # Adjust layer keyframe indices and frame-range properties by the trim offset
        new_max = self.total_frames - 1
        for layer in self.layers:
            for kf in layer.keyframes:
                kf.frame = max(0, min(kf.frame - start, new_max))
            layer.frame_in = max(0, min(layer.frame_in - start, new_max))
            if layer.frame_out >= 0:
                layer.frame_out = max(0, min(layer.frame_out - start, new_max))
            layer.path_start_frame = max(0, min(layer.path_start_frame - start, new_max))
            if layer.path_end_frame >= 0:
                layer.path_end_frame = max(0, min(layer.path_end_frame - start, new_max))
        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, self.total_frames - 1)
        self.frame_slider.setValue(0)
        self.frame_slider.blockSignals(False)
        self.layer_timeline.total_frames = self.total_frames
        self.info_label.setText(f"{self.gif_width}x{self.gif_height} | {self.total_frames}f | {os.path.basename(self.gif_path)}")
        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(f"Trimmed to {self.total_frames} frames")

    def _resize_source(self):
        if not self.gif_pil_frames:
            return
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Resize Source")
        layout = QGridLayout(dlg)
        layout.addWidget(QLabel(f"Current: {self.gif_width}x{self.gif_height}"), 0, 0, 1, 2)
        layout.addWidget(QLabel("Max dimension:"), 1, 0)
        spin_max = QSpinBox()
        spin_max.setRange(16, max(self.gif_width, self.gif_height))
        spin_max.setValue(max(self.gif_width, self.gif_height))
        spin_max.setSingleStep(32)
        layout.addWidget(spin_max, 1, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons, 2, 0, 1, 2)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        max_dim = spin_max.value()
        if max_dim >= max(self.gif_width, self.gif_height):
            return
        ratio = max_dim / max(self.gif_width, self.gif_height)
        new_w = max(1, int(self.gif_width * ratio))
        new_h = max(1, int(self.gif_height * ratio))
        new_pil = []
        new_qpx = []
        for pil_frame in self.gif_pil_frames:
            resized = pil_frame.resize((new_w, new_h), Image.LANCZOS)
            new_pil.append(resized)
            fb = resized.tobytes("raw", "RGBA")
            from PyQt6.QtGui import QImage
            qimg = QImage(fb, new_w, new_h, QImage.Format.Format_RGBA8888)
            new_qpx.append(QPixmap.fromImage(qimg.copy()))
        self.gif_pil_frames = new_pil
        self.gif_frames = new_qpx
        self.gif_width = new_w
        self.gif_height = new_h
        self.info_label.setText(f"{new_w}x{new_h} | {self.total_frames}f | {os.path.basename(self.gif_path)}")
        self._snapshot()
        self._update_all()
        self.statusBar().showMessage(f"Resized to {new_w}x{new_h}")

    def _export_gif(self):
        if not self.gif_pil_frames:
            return

        default_name = os.path.splitext(os.path.basename(self.gif_path))[0] + "_meme.gif"
        default_dir = os.path.dirname(self.gif_path)
        video_filters = ";;MP4 Video (*.mp4);;WebM Video (*.webm)" if HAS_IMAGEIO else ""
        path, filt = QFileDialog.getSaveFileName(
            self, "Export", os.path.join(default_dir, default_name),
            f"GIF (*.gif);;WebP (*.webp);;APNG (*.apng);;PNG Sequence (*.png){video_filters}"
        )
        if not path:
            return
        path, ext = self._resolve_export_target(path, filt)

        layers_payload = [l.to_dict() for l in self.layers]
        worker = ExportWorker(
            self.gif_pil_frames,
            layers_payload,
            self.frame_durations,
            self.total_frames,
            path,
            ext,
        )
        self._start_worker("Export", worker, self._on_export_finished)

    def _export_size_target(self):
        if not self.gif_pil_frames:
            return
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Size-Target Export")
        layout = QGridLayout(dlg)
        layout.addWidget(QLabel("Max file size (MB):"), 0, 0)
        spin_mb = QDoubleSpinBox()
        spin_mb.setRange(0.1, 500.0)
        spin_mb.setValue(10.0)
        spin_mb.setSingleStep(1.0)
        spin_mb.setDecimals(1)
        layout.addWidget(spin_mb, 0, 1)
        layout.addWidget(QLabel("Format:"), 1, 0)
        fmt_combo = QComboBox()
        fmt_combo.addItems(["GIF", "WebP"])
        layout.addWidget(fmt_combo, 1, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons, 2, 0, 1, 2)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_bytes = int(spin_mb.value() * 1024 * 1024)
        ext = ".gif" if fmt_combo.currentText() == "GIF" else ".webp"
        default_name = os.path.splitext(os.path.basename(self.gif_path))[0] + f"_fit{ext}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export (Size Target)", os.path.join(os.path.dirname(self.gif_path), default_name),
            f"{'GIF' if ext == '.gif' else 'WebP'} (*{ext})"
        )
        if not path:
            return
        if not path.lower().endswith(ext):
            path += ext
        layers_payload = [l.to_dict() for l in self.layers]
        worker = ExportWorker(
            self.gif_pil_frames, layers_payload, self.frame_durations,
            self.total_frames, path, ext, target_size_bytes=target_bytes,
        )
        self._start_worker("Size-target export", worker, self._on_export_finished)

    def _on_export_finished(self, output_path):
        try:
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            self.statusBar().showMessage(f"Exported: {os.path.basename(output_path)} ({size_mb:.1f} MB)")
        except OSError:
            self.statusBar().showMessage(f"Exported: {os.path.basename(output_path)}")


# ============================================================================
#  Entry
# ============================================================================

def cli_render(project_path, output_path, output_format=None):
    project_path = os.path.abspath(project_path)
    if not os.path.isfile(project_path):
        print(f"Error: project file not found: {project_path}", file=sys.stderr)
        return 1

    with open(project_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    gif_path = payload.get("gif_path", "")
    gif_relpath = payload.get("gif_relpath")
    project_dir = os.path.dirname(project_path)
    candidates = [gif_path]
    if gif_relpath:
        candidates.append(os.path.join(project_dir, gif_relpath))
    source = None
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            source = candidate
            break
    if source is None:
        print(f"Error: source GIF not found (tried {candidates})", file=sys.stderr)
        return 1

    with Image.open(source) as img:
        pil_frames = []
        durations = []
        n_frames = getattr(img, "n_frames", 1)
        for i in range(n_frames):
            img.seek(i)
            pil_frames.append(img.convert("RGBA").copy())
            durations.append(max(img.info.get("duration", 100), 20))
    total_frames = len(pil_frames)
    if total_frames < 1:
        print("Error: source file has no frames", file=sys.stderr)
        return 1

    validate_project_payload(payload, total_frames=total_frames)
    layers = [TextLayer.from_dict(d) for d in payload.get("layers", [])]

    if not output_path:
        output_path = os.path.splitext(project_path)[0] + "_rendered.gif"
    ext = output_format or os.path.splitext(output_path)[1].lower()
    if not ext.startswith("."):
        ext = "." + ext

    rendered = []
    for i, pil_frame in enumerate(pil_frames):
        frame = pil_frame.copy()
        for layer in layers:
            if layer.is_visible_at(i, total_frames):
                frame = render_text_pil(frame, layer, i, total_frames)
        rendered.append(frame)
        print(f"Rendered frame {i + 1}/{total_frames}", end="\r")
    print()

    if ext == ".webp":
        rendered[0].save(output_path, save_all=True, append_images=rendered[1:],
                         duration=durations, loop=0, lossless=False, quality=85)
    elif ext == ".png":
        base = os.path.splitext(output_path)[0]
        for i, frame in enumerate(rendered):
            frame.save(f"{base}_{i:04d}.png")
    elif ext in (".mp4", ".webm") and HAS_IMAGEIO:
        import av
        import numpy as _np
        avg_dur = sum(durations) / max(1, len(durations))
        fps = max(1, round(1000.0 / max(1, avg_dur)))
        codec = "libvpx" if ext == ".webm" else "mpeg4"
        container = av.open(output_path, mode="w")
        stream = container.add_stream(codec, rate=fps)
        stream.width = rendered[0].width
        stream.height = rendered[0].height
        stream.pix_fmt = "yuv420p"
        for frame in rendered:
            rgb = _np.asarray(frame.convert("RGB"))
            vf = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            for pkt in stream.encode(vf):
                container.mux(pkt)
        for pkt in stream.encode():
            container.mux(pkt)
        container.close()
    else:
        frames = [f.convert("RGB") for f in rendered]
        frames[0].save(output_path, save_all=True, append_images=frames[1:],
                       duration=durations, loop=0, optimize=False)

    print(f"Exported: {output_path}")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--render":
        import argparse
        parser = argparse.ArgumentParser(prog="GifText", description="Headless project render")
        parser.add_argument("--render", required=True, metavar="PROJECT", help=".giftext project file")
        parser.add_argument("--output", "-o", default="", help="Output path (default: <project>_rendered.gif)")
        parser.add_argument("--format", "-f", default=None, help="Output format: gif, webp, png, mp4, webm")
        args = parser.parse_args()
        sys.exit(cli_render(args.render, args.output, args.format))

    app = QApplication(sys.argv)
    branding_icon = QIcon(str(_branding_icon_path()))
    app.setWindowIcon(branding_icon)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    window = GifTextApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
