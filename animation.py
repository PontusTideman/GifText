import math
import re

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
