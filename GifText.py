#!/usr/bin/env python3
"""
GifText v1.3.5 - Animated GIF Text Editor
Full-featured meme text animator with keyframe animation, onion skinning,
undo/redo, project save/load, drag-resize, text presets, and more.
"""

import multiprocessing
multiprocessing.freeze_support()

import sys
import os
import math
import json
import re
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
    QPlainTextEdit, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal, QSize, QMimeData
from PyQt6.QtGui import (
    QIcon, QPixmap, QImage, QColor, QPainter, QFont, QPen, QBrush,
    QFontMetrics, QPainterPath, QCursor, QWheelEvent, QAction, QLinearGradient
)
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np

VERSION = "1.3.5"

LAYER_COLORS = [
    "#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8", "#cba6f7",
    "#fab387", "#94e2d5", "#f5c2e7", "#74c7ec", "#b4befe",
]

MEME_PRESETS = {
    "Classic Meme": {"font": "Impact", "bold": True, "upper": True, "color": "#ffffff",
                     "outline_color": "#000000", "outline_width": 4, "shadow": False, "size": 52, "bg_box": False},
    "Modern Clean": {"font": "Montserrat", "bold": True, "upper": False, "color": "#ffffff",
                     "outline_color": "#000000", "outline_width": 0, "shadow": True, "size": 36, "bg_box": False},
    "Subtitle": {"font": "Arial", "bold": True, "upper": False, "color": "#ffffff",
                 "outline_color": "#000000", "outline_width": 0, "shadow": False, "size": 28, "bg_box": True},
    "Bold Impact": {"font": "Impact", "bold": True, "upper": True, "color": "#f9e2af",
                    "outline_color": "#1e1e2e", "outline_width": 5, "shadow": True, "size": 60, "bg_box": False},
    "Neon": {"font": "Arial", "bold": True, "upper": False, "color": "#89b4fa",
             "outline_color": "#cba6f7", "outline_width": 3, "shadow": True, "size": 40, "bg_box": False},
}

EASING_CURVES = {
    "linear": ("Linear", (0.0, 0.0, 1.0, 1.0)),
    "ease_in": ("Ease In", (0.42, 0.0, 1.0, 1.0)),
    "ease_out": ("Ease Out", (0.0, 0.0, 0.58, 1.0)),
    "ease_in_out": ("Ease In Out", (0.42, 0.0, 0.58, 1.0)),
    "snappy": ("Snappy", (0.2, 0.9, 0.25, 1.0)),
    "overshoot": ("Overshoot", (0.34, 1.56, 0.64, 1.0)),
}

def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def _bezier_component(p1, p2, t):
    mt = 1.0 - t
    return 3.0 * mt * mt * t * p1 + 3.0 * mt * t * t * p2 + t * t * t


def apply_easing_curve(easing, t):
    t = _clamp01(t)
    _label, curve = EASING_CURVES.get(easing, EASING_CURVES["ease_in_out"])
    x1, y1, x2, y2 = curve
    lo, hi = 0.0, 1.0
    sample = t
    for _ in range(16):
        sample = (lo + hi) / 2.0
        x = _bezier_component(x1, x2, sample)
        if x < t:
            lo = sample
        else:
            hi = sample
    return _clamp01(_bezier_component(y1, y2, sample))


def _normalize_path_points(points):
    normalized = []
    for point in points or []:
        if isinstance(point, dict):
            x, y = point.get("x"), point.get("y")
        else:
            try:
                x, y = point[0], point[1]
            except (TypeError, IndexError):
                continue
        try:
            normalized.append((_clamp01(x), _clamp01(y)))
        except (TypeError, ValueError):
            continue
        if len(normalized) == 4:
            break
    return normalized


def sample_cubic_path(points, t):
    path = _normalize_path_points(points)
    if len(path) != 4:
        raise ValueError("Path animation requires exactly four Bezier points")
    t = _clamp01(t)
    mt = 1.0 - t
    p0, p1, p2, p3 = path
    x = (
        mt * mt * mt * p0[0]
        + 3.0 * mt * mt * t * p1[0]
        + 3.0 * mt * t * t * p2[0]
        + t * t * t * p3[0]
    )
    y = (
        mt * mt * mt * p0[1]
        + 3.0 * mt * mt * t * p1[1]
        + 3.0 * mt * t * t * p2[1]
        + t * t * t * p3[1]
    )
    return _clamp01(x), _clamp01(y)


def build_path_keyframes(layer, points, start_frame, frame_count):
    if frame_count < 2:
        raise ValueError("Path animation needs at least two frames")
    keyframes = []
    denom = max(1, frame_count - 1)
    for offset in range(frame_count):
        frame = start_frame + offset
        x, y = sample_cubic_path(points, offset / denom)
        kf = layer.get_interpolated(frame)
        kf.frame = frame
        kf.x = x
        kf.y = y
        keyframes.append(kf)
    return keyframes


def build_effect_keyframes(layer, effect_name, start_frame, frame_count):
    effect = effect_name.strip().lower()
    if effect not in {"bounce", "wiggle", "shake"}:
        raise ValueError(f"Unknown motion effect: {effect_name}")
    if frame_count < 2:
        raise ValueError("Motion effects need at least two frames")

    keyframes = []
    denom = max(1, frame_count - 1)
    shake_pattern = [
        (-1.0, 0.6, -5.0),
        (0.9, -0.5, 5.0),
        (-0.7, -0.3, -4.0),
        (0.7, 0.4, 4.0),
    ]
    for offset in range(frame_count):
        frame = start_frame + offset
        t = offset / denom
        kf = layer.get_interpolated(frame)
        kf.frame = frame

        if effect == "bounce":
            lift = math.sin(math.pi * t)
            kf.y = _clamp01(kf.y - 0.16 * lift)
            kf.font_size = max(8, int(kf.font_size * (1.0 + 0.10 * lift)))
        elif effect == "wiggle":
            wave = math.sin(math.tau * 3.0 * t)
            kf.x = _clamp01(kf.x + 0.018 * wave)
            kf.rotation += 8.0 * wave
        else:
            if offset == 0 or offset == frame_count - 1:
                dx = dy = rot = 0.0
            else:
                dx, dy, rot = shake_pattern[(offset - 1) % len(shake_pattern)]
                envelope = math.sin(math.pi * t)
                dx *= 0.025 * envelope
                dy *= 0.018 * envelope
                rot *= envelope
            kf.x = _clamp01(kf.x + dx)
            kf.y = _clamp01(kf.y + dy)
            kf.rotation += rot

        keyframes.append(kf)
    return keyframes


def apply_staggered_text(text, mode, frame, start_frame, frames_per_unit):
    mode = (mode or "off").lower()
    if mode == "off" or not text:
        return text

    relative = max(0, frame - start_frame)
    visible_units = relative // max(1, int(frames_per_unit)) + 1

    if mode == "lines":
        return "\n".join(text.split("\n")[:visible_units])
    if mode == "letters":
        return text[:visible_units]
    if mode == "words":
        shown = 0
        output = []
        for token in re.findall(r"\s+|\S+", text):
            if token.isspace():
                if shown > 0:
                    output.append(token)
                continue
            if shown >= visible_units:
                break
            output.append(token)
            shown += 1
        return "".join(output).rstrip()

    return text

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

class TextKeyframe:
    __slots__ = ('frame', 'x', 'y', 'font_size', 'opacity',
                 'color', 'outline_color', 'outline_width', 'outline_opacity',
                 'shadow_color', 'shadow_opacity', 'rotation', 'easing')

    def __init__(self, frame=0, x=0.5, y=0.5, font_size=48, opacity=1.0,
                 color="#ffffff", outline_color="#000000", outline_width=3,
                 outline_opacity=1.0, shadow_color="#000000", shadow_opacity=0.5,
                 rotation=0.0, easing="ease_in_out"):
        self.frame = frame
        self.x = x
        self.y = y
        self.font_size = font_size
        self.opacity = opacity
        self.color = color
        self.outline_color = outline_color
        self.outline_width = outline_width
        self.outline_opacity = _clamp01(outline_opacity)
        self.shadow_color = shadow_color
        self.shadow_opacity = _clamp01(shadow_opacity)
        self.rotation = rotation
        self.easing = easing if easing in EASING_CURVES else "ease_in_out"

    def copy(self):
        return TextKeyframe(
            self.frame, self.x, self.y, self.font_size, self.opacity,
            self.color, self.outline_color, self.outline_width, self.outline_opacity,
            self.shadow_color, self.shadow_opacity, self.rotation, self.easing
        )

    def to_dict(self):
        return {s: getattr(self, s) for s in self.__slots__}

    @staticmethod
    def from_dict(d):
        return TextKeyframe(**{k: d[k] for k in TextKeyframe.__slots__ if k in d})


class TextLayer:
    _counter = 0

    def __init__(self, text="TEXT"):
        TextLayer._counter += 1
        self.id = TextLayer._counter
        self.text = text
        self.font_family = "Impact"
        self.bold = True
        self.italic = False
        self.alignment = "center"
        self.keyframes: list[TextKeyframe] = [TextKeyframe()]
        self.visible = True
        self.shadow = False
        self.uppercase = True
        self.bg_box = False
        self.accent = LAYER_COLORS[(self.id - 1) % len(LAYER_COLORS)]
        self.frame_in = 0
        self.frame_out = -1  # -1 = last frame
        self.fade_in = 0     # frames to fade in
        self.fade_out = 0    # frames to fade out
        self.path_points = []
        self.path_start_frame = 0
        self.path_end_frame = -1
        self.stagger_mode = "off"
        self.stagger_frames = 2

    def is_visible_at(self, frame: int, total_frames: int) -> bool:
        if not self.visible:
            return False
        out = self.frame_out if self.frame_out >= 0 else total_frames - 1
        return self.frame_in <= frame <= out

    def get_fade_opacity(self, frame: int, total_frames: int) -> float:
        out = self.frame_out if self.frame_out >= 0 else total_frames - 1
        fade = 1.0
        if self.fade_in > 0 and frame < self.frame_in + self.fade_in:
            fade = min(fade, (frame - self.frame_in) / self.fade_in)
        if self.fade_out > 0 and frame > out - self.fade_out:
            fade = min(fade, (out - frame) / self.fade_out)
        return max(0.0, min(1.0, fade))

    def get_interpolated(self, frame: int) -> TextKeyframe:
        if not self.keyframes:
            return TextKeyframe(frame)
        if len(self.keyframes) == 1:
            kf = self.keyframes[0].copy()
            kf.frame = frame
            return kf

        sorted_kfs = sorted(self.keyframes, key=lambda k: k.frame)
        if frame <= sorted_kfs[0].frame:
            kf = sorted_kfs[0].copy(); kf.frame = frame; return kf
        if frame >= sorted_kfs[-1].frame:
            kf = sorted_kfs[-1].copy(); kf.frame = frame; return kf

        for i in range(len(sorted_kfs) - 1):
            if sorted_kfs[i].frame <= frame <= sorted_kfs[i + 1].frame:
                k1, k2 = sorted_kfs[i], sorted_kfs[i + 1]
                span = k2.frame - k1.frame
                if span == 0:
                    return k1.copy()
                t = (frame - k1.frame) / span
                t = apply_easing_curve(k1.easing, t)
                return self._lerp(k1, k2, t, frame)
        return sorted_kfs[-1].copy()

    def _lerp(self, k1, k2, t, frame):
        def mix(a, b): return a + (b - a) * t
        def mix_color(c1, c2):
            a, b = QColor(c1), QColor(c2)
            return QColor(int(mix(a.red(), b.red())), int(mix(a.green(), b.green())),
                          int(mix(a.blue(), b.blue()))).name()
        kf = TextKeyframe(frame=frame)
        kf.x = mix(k1.x, k2.x); kf.y = mix(k1.y, k2.y)
        kf.font_size = int(mix(k1.font_size, k2.font_size))
        kf.opacity = mix(k1.opacity, k2.opacity)
        kf.outline_width = int(mix(k1.outline_width, k2.outline_width))
        kf.outline_opacity = mix(k1.outline_opacity, k2.outline_opacity)
        kf.shadow_opacity = mix(k1.shadow_opacity, k2.shadow_opacity)
        kf.rotation = mix(k1.rotation, k2.rotation)
        kf.color = mix_color(k1.color, k2.color)
        kf.outline_color = mix_color(k1.outline_color, k2.outline_color)
        kf.shadow_color = mix_color(k1.shadow_color, k2.shadow_color)
        kf.easing = k1.easing
        return kf

    def get_keyframe_at(self, frame):
        for kf in self.keyframes:
            if kf.frame == frame:
                return kf
        return None

    def set_keyframe(self, kf):
        for i, ex in enumerate(self.keyframes):
            if ex.frame == kf.frame:
                self.keyframes[i] = kf; return
        self.keyframes.append(kf)

    def remove_keyframe(self, frame):
        self.keyframes = [k for k in self.keyframes if k.frame != frame]
        if not self.keyframes:
            self.keyframes = [TextKeyframe()]

    def hit_test(self, rx, ry, frame, scale_factor=1.0):
        kf = self.get_interpolated(frame)
        char_w = (kf.font_size * 0.6 * max(len(l) for l in self.text.split('\n'))) * scale_factor
        char_h = kf.font_size * 1.2 * len(self.text.split('\n')) * scale_factor
        dx, dy = abs(rx - kf.x), abs(ry - kf.y)
        if dx < char_w / 2 + 0.03 and dy < char_h / 2 + 0.03:
            return math.sqrt(dx * dx + dy * dy)
        return None

    def to_dict(self):
        return {
            "text": self.text, "font_family": self.font_family,
            "bold": self.bold, "italic": self.italic, "alignment": self.alignment,
            "visible": self.visible, "shadow": self.shadow, "uppercase": self.uppercase,
            "bg_box": self.bg_box, "frame_in": self.frame_in, "frame_out": self.frame_out,
            "fade_in": self.fade_in, "fade_out": self.fade_out,
            "path_points": [[x, y] for x, y in self.path_points],
            "path_start_frame": self.path_start_frame,
            "path_end_frame": self.path_end_frame,
            "stagger_mode": self.stagger_mode,
            "stagger_frames": self.stagger_frames,
            "keyframes": [kf.to_dict() for kf in self.keyframes],
        }

    @staticmethod
    def from_dict(d):
        layer = TextLayer.__new__(TextLayer)
        TextLayer._counter += 1
        layer.id = TextLayer._counter
        layer.text = d.get("text", "TEXT")
        layer.font_family = d.get("font_family", "Impact")
        layer.bold = d.get("bold", True)
        layer.italic = d.get("italic", False)
        layer.alignment = d.get("alignment", "center")
        layer.visible = d.get("visible", True)
        layer.shadow = d.get("shadow", False)
        layer.uppercase = d.get("uppercase", True)
        layer.bg_box = d.get("bg_box", False)
        layer.frame_in = d.get("frame_in", 0)
        layer.frame_out = d.get("frame_out", -1)
        layer.fade_in = d.get("fade_in", 0)
        layer.fade_out = d.get("fade_out", 0)
        layer.path_points = _normalize_path_points(d.get("path_points", []))
        layer.path_start_frame = int(d.get("path_start_frame", 0))
        layer.path_end_frame = int(d.get("path_end_frame", -1))
        layer.stagger_mode = d.get("stagger_mode", "off")
        if layer.stagger_mode not in {"off", "lines", "words", "letters"}:
            layer.stagger_mode = "off"
        layer.stagger_frames = max(1, int(d.get("stagger_frames", 2)))
        layer.accent = LAYER_COLORS[(layer.id - 1) % len(LAYER_COLORS)]
        layer.keyframes = [TextKeyframe.from_dict(k) for k in d.get("keyframes", [{"frame": 0}])]
        return layer


# ============================================================================
#  Undo System
# ============================================================================

class UndoManager:
    def __init__(self, max_history=50):
        self._history: list[str] = []
        self._index = -1
        self._max = max_history

    def snapshot(self, layers: list[TextLayer]):
        state = json.dumps([l.to_dict() for l in layers], ensure_ascii=False, separators=(",", ":"))
        if 0 <= self._index < len(self._history) and self._history[self._index] == state:
            return
        # Discard redo history
        self._history = self._history[:self._index + 1]
        self._history.append(state)
        if len(self._history) > self._max:
            self._history.pop(0)
        self._index = len(self._history) - 1

    def clear(self):
        self._history.clear()
        self._index = -1

    def undo(self) -> list[TextLayer] | None:
        if self._index <= 0:
            return None
        self._index -= 1
        return self._restore()

    def redo(self) -> list[TextLayer] | None:
        if self._index >= len(self._history) - 1:
            return None
        self._index += 1
        return self._restore()

    def _restore(self) -> list[TextLayer]:
        data = json.loads(self._history[self._index])
        TextLayer._counter = 0
        return [TextLayer.from_dict(d) for d in data]

    @property
    def can_undo(self): return self._index > 0
    @property
    def can_redo(self): return self._index < len(self._history) - 1


# ============================================================================
#  Canvas
# ============================================================================

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
                "Load an animated GIF"
            )

            p.setPen(QColor("#a0acbc"))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(
                QRectF(inner.left(), inner.top() + inner.height() * 0.34, inner.width(), 50),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap),
                "Drop a clip onto the stage or use Load GIF to start tracking text across frames."
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
                if url.toLocalFile().lower().endswith('.gif'):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.gif'):
                # Signal to parent
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

        vis = QPushButton("ON" if layer.visible else "OFF")
        vis.setObjectName("layerAction")
        vis.setFixedSize(42, 26)
        vis.setToolTip("Toggle layer visibility")
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

        self.playing = False
        self.play_speed = 1.0
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self._advance_frame)
        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.setSingleShot(True)
        self.snapshot_timer.timeout.connect(self._snapshot)

        self._recent_files: list[str] = []
        self._load_recent()

        self._build_ui()

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

        self.btn_load = QPushButton("Load GIF")
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

        utility_row.addStretch()

        self.hint_label = QLabel("Drop a GIF to begin, then add a text layer and scrub frame by frame.")
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
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont("Impact"))
        self.font_combo.currentFontChanged.connect(self._on_font_changed)
        tgl.addWidget(self.font_combo, r, 1, 1, 2)
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
        self.btn_copy_kf.clicked.connect(self._copy_keyframe_range)
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

        rl.addStretch()
        right_scroll.setWidget(right_inner)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([940, 360])

        self._set_layer_controls_enabled(False)
        self._refresh_chrome_state()
        self.statusBar().showMessage(f"GifText v{VERSION} - Load a GIF to get started")

    # ================================================================
    #  Helpers
    # ================================================================

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
        if ext in {".gif", ".webp", ".png"}:
            return path, ext

        filt = selected_filter.lower()
        if "webp" in filt:
            ext = ".webp"
        elif "png" in filt:
            ext = ".png"
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
            self.hint_label.setText("Drop a GIF to begin, then add a text layer and scrub frame by frame.")
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
        ] + self.effect_buttons:
            widget.setEnabled(enabled)

    # ================================================================
    #  GIF Loading
    # ================================================================

    def _load_gif(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Animated GIF", "", "GIF Files (*.gif);;All Files (*)"
        )
        if path:
            self._load_gif_from_path(path)

    def _load_gif_from_path(self, path):
        try:
            img = Image.open(path)
            if not hasattr(img, 'n_frames') or img.n_frames < 2:
                self.statusBar().showMessage("Not animated (needs 2+ frames)")
                return

            new_frames: list[QPixmap] = []
            new_pil_frames: list[Image.Image] = []
            new_durations: list[int] = []
            new_width = img.width
            new_height = img.height

            for i in range(img.n_frames):
                img.seek(i)
                frame = img.convert("RGBA")
                new_pil_frames.append(frame.copy())
                new_durations.append(max(img.info.get('duration', 100), 20))
                data = frame.tobytes("raw", "RGBA")
                qimg = QImage(data, frame.width, frame.height, QImage.Format.Format_RGBA8888)
                new_frames.append(QPixmap.fromImage(qimg.copy()))

            self._reset_document_state()
            self.gif_frames = new_frames
            self.gif_pil_frames = new_pil_frames
            self.frame_durations = new_durations
            self.gif_width = new_width
            self.gif_height = new_height
            self.gif_path = path
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
            self.btn_save_proj.setEnabled(True)
            self.layer_timeline.total_frames = self.total_frames
            self._rebuild_layer_list()
            self.info_label.setText(f"{self.gif_width}x{self.gif_height} | {self.total_frames}f | {os.path.basename(path)}")
            self.hint_label.setText("Add a text layer, drag it on the stage, then step through frames.")
            self._refresh_chrome_state()

            self._add_recent(path)
            self._snapshot()
            self._update_all()
            self.statusBar().showMessage(f"Loaded {os.path.basename(path)}")
        except Exception as e:
            self.statusBar().showMessage(f"Error: {e}")

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
        nxt = (self.current_frame + 1) % self.total_frames
        self.frame_slider.setValue(nxt)
        delay = int(self.frame_durations[self.current_frame] / self.play_speed)
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
        self.layers = [l for l in self.layers if l.id != layer_id]
        if self.selected_layer and self.selected_layer.id == layer_id:
            self.selected_layer = self.layers[-1] if self.layers else None
        self._snapshot()
        self._rebuild_layer_list()
        self._update_all()

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
                  self.stagger_combo, self.spin_stagger_frames, self.spin_path_span]:
            w.blockSignals(b)

    def _on_text_changed(self):
        if not self.selected_layer:
            return
        self.selected_layer.text = self.txt_input.toPlainText()
        self._schedule_snapshot(420)
        self._rebuild_layer_list()
        self._update_all()

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

    def _copy_keyframe_range(self):
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
        positions = self._track_positions_from_point(self.current_frame, seed.x, seed.y)
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

    def _track_positions_from_point(self, start_frame, rx, ry):
        positions = self._track_positions_with_object_tracker(start_frame, rx, ry)
        if len(positions) >= 2:
            return positions
        return self._track_positions_with_optical_flow(start_frame, rx, ry)

    def _cv_bgr_frame(self, frame_idx):
        rgb = np.asarray(self.gif_pil_frames[frame_idx].convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def _cv_gray_frame(self, frame_idx):
        rgb = np.asarray(self.gif_pil_frames[frame_idx].convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    def _create_cv_tracker(self):
        sources = [cv2]
        legacy = getattr(cv2, "legacy", None)
        if legacy is not None:
            sources.append(legacy)
        for source in sources:
            for name in ("TrackerCSRT_create", "TrackerKCF_create"):
                factory = getattr(source, name, None)
                if factory is None:
                    continue
                try:
                    return factory()
                except Exception:
                    continue
        return None

    def _track_positions_with_object_tracker(self, start_frame, rx, ry):
        tracker = self._create_cv_tracker()
        if tracker is None:
            return []

        first = self._cv_bgr_frame(start_frame)
        h, w = first.shape[:2]
        cx, cy = rx * w, ry * h
        radius = max(8, min(36, int(min(w, h) * 0.08)))
        x0 = max(0, min(w - 2, int(cx - radius)))
        y0 = max(0, min(h - 2, int(cy - radius)))
        x1 = max(x0 + 2, min(w, int(cx + radius)))
        y1 = max(y0 + 2, min(h, int(cy + radius)))
        bbox = (x0, y0, x1 - x0, y1 - y0)

        try:
            initialized = tracker.init(first, bbox)
        except Exception:
            return []
        if initialized is False:
            return []

        positions = [(start_frame, rx, ry)]
        for frame_idx in range(start_frame + 1, self.total_frames):
            try:
                ok, tracked_box = tracker.update(self._cv_bgr_frame(frame_idx))
            except Exception:
                break
            if not ok:
                break
            x, y, bw, bh = tracked_box
            tx = (x + bw / 2) / max(1, w)
            ty = (y + bh / 2) / max(1, h)
            if not (math.isfinite(tx) and math.isfinite(ty)):
                break
            positions.append((frame_idx, max(0.0, min(1.0, tx)), max(0.0, min(1.0, ty))))
        return positions

    def _track_positions_with_optical_flow(self, start_frame, rx, ry):
        first = self._cv_gray_frame(start_frame)
        h, w = first.shape[:2]
        point = np.array([[[rx * w, ry * h]]], dtype=np.float32)
        positions = [(start_frame, rx, ry)]
        prev = first

        criteria = (
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            24,
            0.01,
        )
        for frame_idx in range(start_frame + 1, self.total_frames):
            nxt = self._cv_gray_frame(frame_idx)
            next_point, status, _err = cv2.calcOpticalFlowPyrLK(
                prev,
                nxt,
                point,
                None,
                winSize=(31, 31),
                maxLevel=3,
                criteria=criteria,
            )
            if next_point is None or status is None or status[0][0] != 1:
                break
            x, y = next_point[0][0]
            if not (math.isfinite(float(x)) and math.isfinite(float(y))):
                break
            if x < 0 or y < 0 or x >= w or y >= h:
                break
            positions.append((frame_idx, float(x) / max(1, w), float(y) / max(1, h)))
            prev = nxt
            point = next_point.reshape(1, 1, 2)
        return positions

    # ================================================================
    #  Undo / Redo
    # ================================================================

    def _snapshot(self):
        if self.snapshot_timer.isActive():
            self.snapshot_timer.stop()
        self.undo_mgr.snapshot(self.layers)
        self._update_undo_btns()

    def _undo(self):
        if self.snapshot_timer.isActive():
            self._snapshot()
        result = self.undo_mgr.undo()
        if result is not None:
            self.layers = result
            self.selected_layer = self.layers[-1] if self.layers else None
            self._rebuild_layer_list()
            self._update_all()
            self.statusBar().showMessage("Undo")

    def _redo(self):
        if self.snapshot_timer.isActive():
            self._snapshot()
        result = self.undo_mgr.redo()
        if result is not None:
            self.layers = result
            self.selected_layer = self.layers[-1] if self.layers else None
            self._rebuild_layer_list()
            self._update_all()
            self.statusBar().showMessage("Redo")

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

    def _save_project(self):
        if not self.gif_path:
            return
        default = os.path.splitext(self.gif_path)[0] + ".giftext"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", default, "GifText Project (*.giftext)"
        )
        if not path:
            return
        try:
            rel_path = os.path.relpath(self.gif_path, os.path.dirname(path))
        except ValueError:
            rel_path = None
        project = {
            "version": VERSION,
            "gif_path": self.gif_path,
            "gif_relpath": rel_path,
            "layers": [l.to_dict() for l in self.layers],
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(project, f, indent=2, ensure_ascii=False)
        self.statusBar().showMessage(f"Project saved: {os.path.basename(path)}")

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Project", "", "GifText Project (*.giftext);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                project = json.load(f)
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
                self.statusBar().showMessage("GIF not found for this project file")
                return

            self._load_gif_from_path(gif_path)
            TextLayer._counter = 0
            self.layers = [TextLayer.from_dict(d) for d in project.get("layers", [])]
            self.selected_layer = self.layers[0] if self.layers else None
            self.undo_mgr.clear()
            self._snapshot()
            self._rebuild_layer_list()
            self._update_all()
            self.statusBar().showMessage(f"Project loaded: {os.path.basename(path)}")
        except Exception as e:
            self.statusBar().showMessage(f"Error loading project: {e}")

    # ================================================================
    #  Recent Files
    # ================================================================

    def _recent_path(self):
        return os.path.join(os.path.expanduser("~"), ".giftext_recent.json")

    def _load_recent(self):
        try:
            with open(self._recent_path(), encoding='utf-8') as f:
                self._recent_files = json.load(f)[:10]
        except Exception:
            self._recent_files = []

    def _add_recent(self, path):
        path = os.path.abspath(path)
        self._recent_files = [p for p in self._recent_files if p != path]
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:10]
        try:
            with open(self._recent_path(), 'w', encoding='utf-8') as f:
                json.dump(self._recent_files, f, ensure_ascii=False)
        except Exception:
            pass

    # ================================================================
    #  Export
    # ================================================================

    def _export_gif(self):
        if not self.gif_pil_frames:
            return

        default_name = os.path.splitext(os.path.basename(self.gif_path))[0] + "_meme.gif"
        default_dir = os.path.dirname(self.gif_path)
        path, filt = QFileDialog.getSaveFileName(
            self, "Export", os.path.join(default_dir, default_name),
            "GIF (*.gif);;WebP (*.webp);;PNG Sequence (*.png)"
        )
        if not path:
            return
        path, ext = self._resolve_export_target(path, filt)

        self.statusBar().showMessage("Exporting...")
        QApplication.processEvents()

        try:
            rendered = []
            for i, pil_frame in enumerate(self.gif_pil_frames):
                frame = pil_frame.copy()
                for layer in self.layers:
                    if not layer.is_visible_at(i, self.total_frames):
                        continue
                    frame = self._render_text_pil(frame, layer, i)
                rendered.append(frame)

            if ext == '.webp':
                rgb_frames = [f.convert("RGBA") for f in rendered]
                rgb_frames[0].save(
                    path, save_all=True, append_images=rgb_frames[1:],
                    duration=self.frame_durations, loop=0, lossless=False, quality=85
                )
            elif ext == '.png':
                # PNG sequence
                base = os.path.splitext(path)[0]
                for i, frame in enumerate(rendered):
                    frame.save(f"{base}_{i:04d}.png")
                self.statusBar().showMessage(f"Exported PNG sequence: {os.path.basename(base)}_0000.png")
                return
            else:
                rgb_frames = [f.convert("RGB") for f in rendered]
                rgb_frames[0].save(
                    path, save_all=True, append_images=rgb_frames[1:],
                    duration=self.frame_durations, loop=0, optimize=False
                )

            self.statusBar().showMessage(f"Exported: {os.path.basename(path)}")
        except Exception as e:
            self.statusBar().showMessage(f"Export error: {e}")

    def _render_text_pil(self, frame, layer, frame_idx):
        kf = layer.get_interpolated(frame_idx)
        text = layer.text.upper() if layer.uppercase else layer.text
        text = apply_staggered_text(text, layer.stagger_mode, frame_idx,
                                    layer.frame_in, layer.stagger_frames)
        if not text:
            return frame

        fade = layer.get_fade_opacity(frame_idx, self.total_frames)
        effective_alpha = int(kf.opacity * fade * 255)
        if effective_alpha <= 0:
            return frame

        overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = self._get_pil_font(layer, kf.font_size)

        lines = text.split('\n')
        line_sizes = []
        total_h = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
            line_sizes.append((lw, lh))
            total_h += lh

        cx = kf.x * frame.width
        cy = kf.y * frame.height
        y_cursor = cy - total_h / 2

        text_rgb = tuple(int(kf.color[i:i+2], 16) for i in (1, 3, 5))
        outline_rgb = tuple(int(kf.outline_color[i:i+2], 16) for i in (1, 3, 5))
        shadow_rgb = tuple(int(kf.shadow_color[i:i+2], 16) for i in (1, 3, 5))
        outline_alpha = int(effective_alpha * kf.outline_opacity)
        shadow_alpha = int(effective_alpha * kf.shadow_opacity)

        # Background box
        if layer.bg_box:
            max_lw = max(s[0] for s in line_sizes)
            box_rect = [cx - max_lw / 2 - 8, cy - total_h / 2 - 8,
                        cx + max_lw / 2 + 8, cy + total_h / 2 + 8]
            draw.rounded_rectangle(box_rect, radius=4,
                                   fill=(0, 0, 0, int(160 * kf.opacity * fade)))

        for i, line in enumerate(lines):
            lw, lh = line_sizes[i]
            max_w = max(s[0] for s in line_sizes)
            if layer.alignment == "center":
                lx = cx - lw / 2
            elif layer.alignment == "left":
                lx = cx - max_w / 2
            else:
                lx = cx + max_w / 2 - lw

            if kf.outline_width > 0:
                try:
                    draw.text((lx, y_cursor), line, font=font,
                              fill=(*outline_rgb, outline_alpha),
                              stroke_width=kf.outline_width,
                              stroke_fill=(*outline_rgb, outline_alpha))
                except TypeError:
                    ow = kf.outline_width
                    for dx in range(-ow, ow + 1):
                        for dy in range(-ow, ow + 1):
                            if dx * dx + dy * dy <= ow * ow:
                                draw.text((lx + dx, y_cursor + dy), line, font=font,
                                          fill=(*outline_rgb, outline_alpha))

            if layer.shadow:
                draw.text((lx + 2, y_cursor + 2), line, font=font,
                          fill=(*shadow_rgb, shadow_alpha))

            draw.text((lx, y_cursor), line, font=font, fill=(*text_rgb, effective_alpha))
            y_cursor += lh

        if kf.rotation != 0:
            overlay = overlay.rotate(-kf.rotation, center=(cx, cy),
                                     resample=Image.Resampling.BICUBIC, expand=False)

        return Image.alpha_composite(frame, overlay)

    def _get_pil_font(self, layer, size):
        family = layer.font_family.lower().replace(' ', '')
        candidates = []
        if layer.bold and layer.italic:
            candidates += [f"{family}bi.ttf", f"{family}z.ttf"]
        if layer.bold:
            candidates += [f"{family}bd.ttf", f"{family}b.ttf"]
        if layer.italic:
            candidates.append(f"{family}i.ttf")
        candidates.append(f"{family}.ttf")
        candidates += ["impact.ttf", "arialbd.ttf", "arial.ttf"]
        for name in candidates:
            try:
                return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
            except Exception:
                continue
        return ImageFont.load_default()


# ============================================================================
#  Entry
# ============================================================================

def main():
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
