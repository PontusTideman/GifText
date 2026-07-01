import json
import math

from PyQt6.QtGui import QColor

from animation import (
    EASING_CURVES,
    _clamp01,
    _normalize_path_points,
    apply_easing_curve,
)

VERSION = "1.5.0"
PROJECT_SCHEMA_VERSION = 2

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
        self.frame_out = -1
        self.fade_in = 0
        self.fade_out = 0
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


class UndoManager:
    def __init__(self, max_history=50):
        self._history: list[str] = []
        self._index = -1
        self._max = max_history

    def snapshot(self, layers: list[TextLayer]):
        state = json.dumps([l.to_dict() for l in layers], ensure_ascii=False, separators=(",", ":"))
        if 0 <= self._index < len(self._history) and self._history[self._index] == state:
            return
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
