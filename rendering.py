from PIL import Image, ImageDraw, ImageFont

from animation import apply_staggered_text

UNICODE_FALLBACK_FONTS = [
    "segoeui.ttf",
    "seguisym.ttf",
    "seguiemj.ttf",
    "arialuni.ttf",
    "nirmala.ttf",
    "malgun.ttf",
    "meiryo.ttc",
    "msgothic.ttc",
    "msyh.ttc",
    "simsun.ttc",
    "arial.ttf",
]


def get_pil_font(layer, size, sample_text=""):
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
    if any(ord(char) > 127 for char in sample_text or ""):
        candidates = candidates + [name for name in UNICODE_FALLBACK_FONTS if name not in candidates]
    for name in candidates:
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_text_pil(frame, layer, frame_idx, total_frames):
    kf = layer.get_interpolated(frame_idx)
    text = layer.text.upper() if layer.uppercase else layer.text
    text = apply_staggered_text(text, layer.stagger_mode, frame_idx,
                                layer.frame_in, layer.stagger_frames)
    if not text:
        return frame

    fade = layer.get_fade_opacity(frame_idx, total_frames)
    effective_alpha = int(kf.opacity * fade * 255)
    if effective_alpha <= 0:
        return frame

    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = get_pil_font(layer, kf.font_size, text)

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
