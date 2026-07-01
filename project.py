import math
import os
import re

from PyQt6.QtGui import QColor

from animation import EASING_CURVES
from models import (
    PROJECT_SCHEMA_VERSION,
    VERSION,
    TextKeyframe,
    TextLayer,
)


class ProjectValidationError(ValueError):
    pass


def _is_int_value(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_bool(value, label):
    if not isinstance(value, bool):
        raise ProjectValidationError(f"{label} must be true or false")


def _validate_int(value, label, minimum=None, maximum=None):
    if not _is_int_value(value):
        raise ProjectValidationError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ProjectValidationError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ProjectValidationError(f"{label} must be at most {maximum}")


def _validate_float(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ProjectValidationError(f"{label} must be a finite number")
    if minimum is not None and float(value) < minimum:
        raise ProjectValidationError(f"{label} must be at least {minimum}")
    if maximum is not None and float(value) > maximum:
        raise ProjectValidationError(f"{label} must be at most {maximum}")


def _validate_color_value(value, label):
    if not isinstance(value, str) or not QColor(value).isValid():
        raise ProjectValidationError(f"{label} must be a valid color")


def validate_project_payload(project, total_frames=None):
    if not isinstance(project, dict):
        raise ProjectValidationError("Project file must contain a JSON object")

    schema_version = project.get("schema_version", 1)
    if not _is_int_value(schema_version):
        raise ProjectValidationError("schema_version must be an integer")
    if schema_version < 1:
        raise ProjectValidationError("schema_version must be at least 1")
    if schema_version > PROJECT_SCHEMA_VERSION:
        raise ProjectValidationError(
            f"schema_version {schema_version} is newer than this app supports ({PROJECT_SCHEMA_VERSION})"
        )

    for field in ("gif_path", "gif_relpath", "version"):
        if field in project and project[field] is not None and not isinstance(project[field], str):
            raise ProjectValidationError(f"{field} must be text")

    if total_frames is not None:
        _validate_int(total_frames, "total_frames", 1)
        max_frame = total_frames - 1
    else:
        max_frame = None

    layers = project.get("layers")
    if not isinstance(layers, list):
        raise ProjectValidationError("layers must be a list")

    for layer_index, layer in enumerate(layers):
        label = f"layers[{layer_index}]"
        if not isinstance(layer, dict):
            raise ProjectValidationError(f"{label} must be an object")
        for field in ("text", "font_family"):
            if field in layer and not isinstance(layer[field], str):
                raise ProjectValidationError(f"{label}.{field} must be text")
        if "alignment" in layer and layer["alignment"] not in {"center", "left", "right"}:
            raise ProjectValidationError(f"{label}.alignment must be center, left, or right")
        for field in ("bold", "italic", "visible", "shadow", "uppercase", "bg_box"):
            if field in layer:
                _validate_bool(layer[field], f"{label}.{field}")

        frame_in = layer.get("frame_in", 0)
        frame_out = layer.get("frame_out", -1)
        _validate_int(frame_in, f"{label}.frame_in", 0, max_frame)
        _validate_int(frame_out, f"{label}.frame_out", -1, max_frame)
        if frame_out >= 0 and frame_out < frame_in:
            raise ProjectValidationError(f"{label}.frame_out must be -1 or at least frame_in")
        _validate_int(layer.get("fade_in", 0), f"{label}.fade_in", 0, 100)
        _validate_int(layer.get("fade_out", 0), f"{label}.fade_out", 0, 100)
        _validate_int(layer.get("path_start_frame", 0), f"{label}.path_start_frame", 0, max_frame)
        _validate_int(layer.get("path_end_frame", -1), f"{label}.path_end_frame", -1, max_frame)

        stagger_mode = layer.get("stagger_mode", "off")
        if stagger_mode not in {"off", "lines", "words", "letters"}:
            raise ProjectValidationError(f"{label}.stagger_mode is invalid")
        _validate_int(layer.get("stagger_frames", 2), f"{label}.stagger_frames", 1, 60)

        path_points = layer.get("path_points", [])
        if not isinstance(path_points, list):
            raise ProjectValidationError(f"{label}.path_points must be a list")
        if path_points and len(path_points) != 4:
            raise ProjectValidationError(f"{label}.path_points must contain exactly four points")
        for point_index, point in enumerate(path_points):
            point_label = f"{label}.path_points[{point_index}]"
            if isinstance(point, dict):
                x, y = point.get("x"), point.get("y")
            elif isinstance(point, (list, tuple)) and len(point) == 2:
                x, y = point[0], point[1]
            else:
                raise ProjectValidationError(f"{point_label} must be [x, y]")
            _validate_float(x, f"{point_label}.x", 0.0, 1.0)
            _validate_float(y, f"{point_label}.y", 0.0, 1.0)

        keyframes = layer.get("keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            raise ProjectValidationError(f"{label}.keyframes must be a non-empty list")
        seen_frames = set()
        for keyframe_index, keyframe in enumerate(keyframes):
            klabel = f"{label}.keyframes[{keyframe_index}]"
            if not isinstance(keyframe, dict):
                raise ProjectValidationError(f"{klabel} must be an object")
            frame = keyframe.get("frame")
            _validate_int(frame, f"{klabel}.frame", 0, max_frame)
            if frame in seen_frames:
                raise ProjectValidationError(f"{klabel}.frame duplicates another keyframe")
            seen_frames.add(frame)

            if "x" in keyframe:
                _validate_float(keyframe["x"], f"{klabel}.x", 0.0, 1.0)
            if "y" in keyframe:
                _validate_float(keyframe["y"], f"{klabel}.y", 0.0, 1.0)
            if "font_size" in keyframe:
                _validate_int(keyframe["font_size"], f"{klabel}.font_size", 8, 200)
            if "opacity" in keyframe:
                _validate_float(keyframe["opacity"], f"{klabel}.opacity", 0.0, 1.0)
            if "outline_width" in keyframe:
                _validate_int(keyframe["outline_width"], f"{klabel}.outline_width", 0, 20)
            if "outline_opacity" in keyframe:
                _validate_float(keyframe["outline_opacity"], f"{klabel}.outline_opacity", 0.0, 1.0)
            if "shadow_opacity" in keyframe:
                _validate_float(keyframe["shadow_opacity"], f"{klabel}.shadow_opacity", 0.0, 1.0)
            if "rotation" in keyframe:
                _validate_float(keyframe["rotation"], f"{klabel}.rotation", -360.0, 360.0)
            for field in ("color", "outline_color", "shadow_color"):
                if field in keyframe:
                    _validate_color_value(keyframe[field], f"{klabel}.{field}")
            if "easing" in keyframe and keyframe["easing"] not in EASING_CURVES:
                raise ProjectValidationError(f"{klabel}.easing is invalid")


def build_project_payload(gif_path, layers, project_path=None):
    rel_path = None
    if project_path:
        try:
            rel_path = os.path.relpath(gif_path, os.path.dirname(project_path))
        except ValueError:
            rel_path = None
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "version": VERSION,
        "gif_path": gif_path,
        "gif_relpath": rel_path,
        "layers": [layer.to_dict() for layer in layers],
    }


def parse_subtitle_timestamp(value):
    match = re.match(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})([,.](\d{1,3}))?\s*$", value)
    if not match:
        raise ValueError(f"Invalid subtitle timestamp: {value}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    millis = int((match.group(5) or "0").ljust(3, "0")[:3])
    return hours * 3600.0 + minutes * 60.0 + seconds + millis / 1000.0


def parse_subtitle_text(text):
    entries = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    for block in blocks:
        lines = [line.strip("﻿") for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if lines[0].strip().upper().startswith("WEBVTT"):
            continue
        if re.fullmatch(r"\d+", lines[0].strip()) and len(lines) > 1:
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_raw, end_raw = [part.strip().split()[0] for part in lines[0].split("-->", 1)]
        caption = "\n".join(line.strip() for line in lines[1:]).strip()
        if not caption:
            continue
        entries.append((parse_subtitle_timestamp(start_raw), parse_subtitle_timestamp(end_raw), caption))
    return entries


def frame_for_time(seconds, frame_durations, total_frames):
    if total_frames <= 1:
        return 0
    target_ms = max(0.0, seconds * 1000.0)
    elapsed = 0.0
    for idx, duration in enumerate(frame_durations[:total_frames]):
        elapsed += max(1, int(duration))
        if target_ms < elapsed:
            return idx
    return total_frames - 1


def subtitle_entries_to_layers(entries, frame_durations, total_frames):
    layers = []
    for start_seconds, end_seconds, caption in entries:
        start_frame = frame_for_time(start_seconds, frame_durations, total_frames)
        end_frame = frame_for_time(max(start_seconds, end_seconds), frame_durations, total_frames)
        if end_frame < start_frame:
            end_frame = start_frame
        layer = TextLayer(caption)
        layer.uppercase = False
        layer.alignment = "center"
        layer.frame_in = start_frame
        layer.frame_out = end_frame
        layer.fade_in = 1
        layer.fade_out = 1
        layer.bg_box = True
        layer.keyframes = [
            TextKeyframe(
                frame=start_frame,
                x=0.5,
                y=0.84,
                font_size=30,
                color="#ffffff",
                outline_color="#000000",
                outline_width=2,
                outline_opacity=0.9,
            )
        ]
        layers.append(layer)
    return layers
