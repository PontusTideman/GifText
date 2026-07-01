import math
import os

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
import cv2
import numpy as np

from models import TextLayer
from rendering import render_text_pil

try:
    import imageio.v3 as iio
    HAS_IMAGEIO = True
except ImportError:
    HAS_IMAGEIO = False

VIDEO_EXTENSIONS = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".m4v"}


class CancelableWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def _is_canceled(self):
        return self._cancel_requested


class LoadGifWorker(CancelableWorker):
    def __init__(self, path):
        super().__init__()
        self.path = path

    @pyqtSlot()
    def run(self):
        try:
            with Image.open(self.path) as img:
                if not hasattr(img, 'n_frames') or img.n_frames < 2:
                    self.failed.emit("Not animated (needs 2+ frames)")
                    return

                pil_frames = []
                frame_bytes = []
                durations = []
                total = img.n_frames
                width = img.width
                height = img.height
                for i in range(total):
                    if self._is_canceled():
                        self.canceled.emit()
                        return
                    img.seek(i)
                    frame = img.convert("RGBA")
                    pil_frames.append(frame.copy())
                    frame_bytes.append(frame.tobytes("raw", "RGBA"))
                    durations.append(max(img.info.get('duration', 100), 20))
                    self.progress.emit(int((i + 1) / total * 100), f"Loading frame {i + 1} of {total}")

                self.finished.emit({
                    "path": self.path,
                    "width": width,
                    "height": height,
                    "pil_frames": pil_frames,
                    "frame_bytes": frame_bytes,
                    "durations": durations,
                })
        except Exception as exc:
            self.failed.emit(str(exc))


class LoadVideoWorker(CancelableWorker):
    def __init__(self, path, target_fps=10, max_frames=200, max_size=0,
                 trim_start=0.0, trim_end=0.0):
        super().__init__()
        self.path = path
        self.target_fps = target_fps
        self.max_frames = max_frames
        self.max_size = max_size
        self.trim_start = trim_start
        self.trim_end = trim_end

    @pyqtSlot()
    def run(self):
        if not HAS_IMAGEIO:
            self.failed.emit("imageio is not installed (pip install imageio imageio-ffmpeg)")
            return
        try:
            meta = iio.immeta(self.path, plugin="pyav")
            video_fps = meta.get("fps", 30)
            duration = meta.get("duration", 0)
            if duration <= 0:
                self.failed.emit("Could not determine video duration")
                return

            actual_start = self.trim_start
            actual_end = self.trim_end if self.trim_end > 0 else duration
            actual_end = min(actual_end, duration)
            if actual_start >= actual_end:
                self.failed.emit("Trim range is empty")
                return

            clip_duration = actual_end - actual_start
            step = max(1, int(round(video_fps / self.target_fps)))
            frame_duration_ms = int(round(1000.0 / self.target_fps))
            start_frame_idx = int(actual_start * video_fps)
            end_frame_idx = int(actual_end * video_fps)

            pil_frames = []
            frame_bytes = []
            durations = []
            width = height = 0
            frame_idx = 0
            sampled = 0

            for raw_frame in iio.imiter(self.path, plugin="pyav"):
                if self._is_canceled():
                    self.canceled.emit()
                    return
                if frame_idx < start_frame_idx:
                    frame_idx += 1
                    continue
                if frame_idx >= end_frame_idx:
                    break
                if (frame_idx - start_frame_idx) % step != 0:
                    frame_idx += 1
                    continue

                frame = Image.fromarray(raw_frame).convert("RGBA")
                if self.max_size > 0 and (frame.width > self.max_size or frame.height > self.max_size):
                    ratio = self.max_size / max(frame.width, frame.height)
                    new_w = max(1, int(frame.width * ratio))
                    new_h = max(1, int(frame.height * ratio))
                    frame = frame.resize((new_w, new_h), Image.LANCZOS)
                if width == 0:
                    width, height = frame.width, frame.height
                pil_frames.append(frame)
                frame_bytes.append(frame.tobytes("raw", "RGBA"))
                durations.append(frame_duration_ms)
                sampled += 1
                progress = min(99, int((frame_idx - start_frame_idx) / max(1, end_frame_idx - start_frame_idx) * 100))
                self.progress.emit(progress, f"Reading frame {sampled}")
                if sampled >= self.max_frames:
                    break
                frame_idx += 1

            if len(pil_frames) < 2:
                self.failed.emit("Video produced fewer than 2 frames at the selected settings")
                return

            self.finished.emit({
                "path": self.path,
                "width": width,
                "height": height,
                "pil_frames": pil_frames,
                "frame_bytes": frame_bytes,
                "durations": durations,
            })
        except Exception as exc:
            self.failed.emit(str(exc))


def get_video_metadata(path):
    if not HAS_IMAGEIO:
        return None
    try:
        meta = iio.immeta(path, plugin="pyav")
        return {
            "fps": meta.get("fps", 30),
            "duration": meta.get("duration", 0),
            "size": meta.get("size", (0, 0)),
        }
    except Exception:
        return None


class TrackingWorker(CancelableWorker):
    def __init__(self, pil_frames, start_frame, rx, ry):
        super().__init__()
        self.pil_frames = list(pil_frames)
        self.start_frame = start_frame
        self.rx = rx
        self.ry = ry

    @pyqtSlot()
    def run(self):
        try:
            self.pil_frames = [frame.copy() for frame in self.pil_frames]
            positions = self._track_positions_with_object_tracker()
            if self._is_canceled():
                self.canceled.emit()
                return
            if len(positions) < 2:
                positions = self._track_positions_with_optical_flow()
            if self._is_canceled():
                self.canceled.emit()
                return
            self.finished.emit(positions)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _cv_bgr_frame(self, frame_idx):
        rgb = np.asarray(self.pil_frames[frame_idx].convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def _cv_gray_frame(self, frame_idx):
        rgb = np.asarray(self.pil_frames[frame_idx].convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    def _create_cv_tracker(self):
        factories = [
            ("TrackerCSRT_create", getattr(cv2, "TrackerCSRT_create", None)),
            ("TrackerKCF_create", getattr(cv2, "TrackerKCF_create", None)),
        ]
        legacy = getattr(cv2, "legacy", None)
        if legacy is not None:
            factories.extend([
                ("legacy.TrackerCSRT_create", getattr(legacy, "TrackerCSRT_create", None)),
                ("legacy.TrackerKCF_create", getattr(legacy, "TrackerKCF_create", None)),
            ])
        for _name, factory in factories:
            if factory is None:
                continue
            try:
                return factory()
            except Exception:
                continue
        return None

    def _track_positions_with_object_tracker(self):
        tracker = self._create_cv_tracker()
        if tracker is None:
            return []
        first = self._cv_bgr_frame(self.start_frame)
        h, w = first.shape[:2]
        box_w = max(12, int(w * 0.12))
        box_h = max(12, int(h * 0.12))
        cx = int(self.rx * w)
        cy = int(self.ry * h)
        x = max(0, min(w - box_w, cx - box_w // 2))
        y = max(0, min(h - box_h, cy - box_h // 2))
        bbox = (x, y, box_w, box_h)
        try:
            initialized = tracker.init(first, bbox)
        except Exception:
            return []
        if not initialized:
            return []

        positions = [(self.start_frame, self.rx, self.ry)]
        total = len(self.pil_frames)
        for frame_idx in range(self.start_frame + 1, total):
            if self._is_canceled():
                return positions
            ok, tracked_box = tracker.update(self._cv_bgr_frame(frame_idx))
            if not ok:
                break
            x, y, bw, bh = tracked_box
            tx = (x + bw / 2) / max(1, w)
            ty = (y + bh / 2) / max(1, h)
            if not (math.isfinite(tx) and math.isfinite(ty)):
                break
            positions.append((frame_idx, max(0.0, min(1.0, tx)), max(0.0, min(1.0, ty))))
            self.progress.emit(int((frame_idx + 1) / total * 100), f"Tracking frame {frame_idx + 1} of {total}")
        return positions

    def _track_positions_with_optical_flow(self):
        first = self._cv_gray_frame(self.start_frame)
        h, w = first.shape[:2]
        point = np.array([[[self.rx * w, self.ry * h]]], dtype=np.float32)
        positions = [(self.start_frame, self.rx, self.ry)]
        prev = first
        total = len(self.pil_frames)

        criteria = (
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            24,
            0.01,
        )
        for frame_idx in range(self.start_frame + 1, total):
            if self._is_canceled():
                return positions
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
            self.progress.emit(int((frame_idx + 1) / total * 100), f"Tracking frame {frame_idx + 1} of {total}")
        return positions


class ExportWorker(CancelableWorker):
    def __init__(self, pil_frames, layers_payload, frame_durations, total_frames, path, ext):
        super().__init__()
        self.pil_frames = [frame.copy() for frame in pil_frames]
        self.layers_payload = layers_payload
        self.frame_durations = list(frame_durations)
        self.total_frames = total_frames
        self.path = path
        self.ext = ext

    @pyqtSlot()
    def run(self):
        try:
            old_counter = TextLayer._counter
            try:
                layers = [TextLayer.from_dict(d) for d in self.layers_payload]
            finally:
                TextLayer._counter = old_counter
            rendered = []
            total = len(self.pil_frames)
            for i, pil_frame in enumerate(self.pil_frames):
                if self._is_canceled():
                    self.canceled.emit()
                    return
                frame = pil_frame.copy()
                for layer in layers:
                    if not layer.is_visible_at(i, self.total_frames):
                        continue
                    frame = render_text_pil(frame, layer, i, self.total_frames)
                rendered.append(frame)
                self.progress.emit(int((i + 1) / total * 70), f"Rendering frame {i + 1} of {total}")

            if self._is_canceled():
                self.canceled.emit()
                return

            if self.ext in ('.mp4', '.webm') and HAS_IMAGEIO:
                import av
                avg_duration = sum(self.frame_durations) / max(1, len(self.frame_durations))
                fps = max(1, round(1000.0 / max(1, avg_duration)))
                codec = "libvpx" if self.ext == ".webm" else "mpeg4"
                pix_fmt = "yuv420p"
                container = av.open(self.path, mode="w")
                stream = container.add_stream(codec, rate=fps)
                stream.width = rendered[0].width
                stream.height = rendered[0].height
                stream.pix_fmt = pix_fmt
                for i, frame in enumerate(rendered):
                    if self._is_canceled():
                        container.close()
                        try:
                            os.remove(self.path)
                        except OSError:
                            pass
                        self.canceled.emit()
                        return
                    import numpy as _np
                    rgb = _np.asarray(frame.convert("RGB"))
                    video_frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
                    for packet in stream.encode(video_frame):
                        container.mux(packet)
                    self.progress.emit(70 + int((i + 1) / total * 30), f"Encoding frame {i + 1} of {total}")
                for packet in stream.encode():
                    container.mux(packet)
                container.close()
                output = self.path
            elif self.ext == '.webp':
                frames = [f.convert("RGBA") for f in rendered]
                frames[0].save(
                    self.path, save_all=True, append_images=frames[1:],
                    duration=self.frame_durations, loop=0, lossless=False, quality=85
                )
                output = self.path
            elif self.ext == '.png':
                base = os.path.splitext(self.path)[0]
                written = []
                for i, frame in enumerate(rendered):
                    if self._is_canceled():
                        for filename in written:
                            try:
                                os.remove(filename)
                            except OSError:
                                pass
                        self.canceled.emit()
                        return
                    filename = f"{base}_{i:04d}.png"
                    frame.save(filename)
                    written.append(filename)
                    self.progress.emit(70 + int((i + 1) / total * 30), f"Saving PNG {i + 1} of {total}")
                output = f"{base}_0000.png"
            else:
                frames = [f.convert("RGB") for f in rendered]
                frames[0].save(
                    self.path, save_all=True, append_images=frames[1:],
                    duration=self.frame_durations, loop=0, optimize=False
                )
                output = self.path

            self.progress.emit(100, "Export complete")
            self.finished.emit(output)
        except Exception as exc:
            self.failed.emit(str(exc))
