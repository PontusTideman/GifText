#!/usr/bin/env python3

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from GifText import (
    DiagnosticsRecorder,
    ExportWorker,
    GifTextApp,
    HAS_IMAGEIO,
    LoadGifWorker,
    LoadVideoWorker,
    PROJECT_SCHEMA_VERSION,
    ProjectValidationError,
    TextKeyframe,
    TextLayer,
    VERSION,
    VIDEO_EXTENSIONS,
    apply_easing_curve,
    apply_staggered_text,
    build_diagnostics_bundle,
    build_project_payload,
    build_effect_keyframes,
    build_path_keyframes,
    cli_render,
    get_pil_font,
    get_video_metadata,
    render_text_pil,
    sample_cubic_path,
    parse_subtitle_text,
    subtitle_entries_to_layers,
    validate_project_payload,
)
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication


class PathAnimationTests(unittest.TestCase):
    def test_cubic_path_samples_endpoints_and_midpoint(self):
        points = [(0.1, 0.2), (0.3, 0.0), (0.8, 1.0), (0.9, 0.7)]

        self.assertEqual(sample_cubic_path(points, 0.0), (0.1, 0.2))
        self.assertEqual(sample_cubic_path(points, 1.0), (0.9, 0.7))

        mid_x, mid_y = sample_cubic_path(points, 0.5)
        self.assertGreater(mid_x, 0.1)
        self.assertLess(mid_x, 0.9)
        self.assertGreater(mid_y, 0.2)
        self.assertLess(mid_y, 0.7)

    def test_path_keyframes_preserve_non_position_properties(self):
        layer = TextLayer("path")
        layer.keyframes = [
            TextKeyframe(frame=0, x=0.0, y=0.0, font_size=40, opacity=0.5, rotation=15.0),
            TextKeyframe(frame=3, x=1.0, y=1.0, font_size=80, opacity=1.0, rotation=45.0),
        ]
        points = [(0.0, 0.25), (0.25, 0.0), (0.75, 1.0), (1.0, 0.75)]

        keyframes = build_path_keyframes(layer, points, start_frame=0, frame_count=4)

        self.assertEqual([kf.frame for kf in keyframes], [0, 1, 2, 3])
        self.assertEqual((keyframes[0].x, keyframes[0].y), (0.0, 0.25))
        self.assertEqual((keyframes[-1].x, keyframes[-1].y), (1.0, 0.75))
        self.assertEqual(keyframes[0].font_size, 40)
        self.assertEqual(keyframes[-1].font_size, 80)
        self.assertAlmostEqual(keyframes[-1].rotation, 45.0)

    def test_easing_curves_change_interpolated_timing(self):
        self.assertAlmostEqual(apply_easing_curve("linear", 0.5), 0.5, places=3)
        self.assertLess(apply_easing_curve("ease_in", 0.5), 0.5)
        self.assertGreater(apply_easing_curve("ease_out", 0.5), 0.5)

        layer = TextLayer("ease")
        layer.keyframes = [
            TextKeyframe(frame=0, x=0.0, y=0.5, easing="linear"),
            TextKeyframe(frame=10, x=1.0, y=0.5),
        ]
        self.assertAlmostEqual(layer.get_interpolated(5).x, 0.5, places=3)

        layer.keyframes[0].easing = "ease_in"
        self.assertLess(layer.get_interpolated(5).x, 0.5)

    def test_layer_path_metadata_round_trips(self):
        layer = TextLayer("round trip")
        layer.path_points = [(0.1, 0.2), (0.3, 0.4), (0.5, 0.6), (0.7, 0.8)]
        layer.path_start_frame = 2
        layer.path_end_frame = 12
        layer.stagger_mode = "words"
        layer.stagger_frames = 3
        layer.keyframes[0].easing = "overshoot"
        layer.keyframes[0].outline_opacity = 0.4
        layer.keyframes[0].shadow_color = "#112233"
        layer.keyframes[0].shadow_opacity = 0.3

        restored = TextLayer.from_dict(layer.to_dict())

        self.assertEqual(restored.path_points, layer.path_points)
        self.assertEqual(restored.path_start_frame, 2)
        self.assertEqual(restored.path_end_frame, 12)
        self.assertEqual(restored.stagger_mode, "words")
        self.assertEqual(restored.stagger_frames, 3)
        self.assertEqual(restored.keyframes[0].easing, "overshoot")
        self.assertAlmostEqual(restored.keyframes[0].outline_opacity, 0.4)
        self.assertEqual(restored.keyframes[0].shadow_color, "#112233")
        self.assertAlmostEqual(restored.keyframes[0].shadow_opacity, 0.3)

    def test_stroke_shadow_fields_interpolate(self):
        layer = TextLayer("render fields")
        layer.keyframes = [
            TextKeyframe(frame=0, outline_opacity=0.2, shadow_opacity=0.1, shadow_color="#000000"),
            TextKeyframe(frame=10, outline_opacity=0.8, shadow_opacity=0.7, shadow_color="#ffffff"),
        ]

        mid = layer.get_interpolated(5)

        self.assertGreater(mid.outline_opacity, 0.2)
        self.assertLess(mid.outline_opacity, 0.8)
        self.assertGreater(mid.shadow_opacity, 0.1)
        self.assertLess(mid.shadow_opacity, 0.7)
        self.assertNotEqual(mid.shadow_color, "#000000")

    def test_staggered_text_reveals_lines_words_and_letters(self):
        text = "Top line\nBottom line"
        self.assertEqual(apply_staggered_text(text, "lines", 0, 0, 2), "Top line")
        self.assertEqual(apply_staggered_text(text, "lines", 2, 0, 2), text)

        words = "one two\nthree"
        self.assertEqual(apply_staggered_text(words, "words", 0, 0, 1), "one")
        self.assertEqual(apply_staggered_text(words, "words", 1, 0, 1), "one two")
        self.assertEqual(apply_staggered_text(words, "words", 2, 0, 1), words)

        self.assertEqual(apply_staggered_text("HELLO", "letters", 2, 0, 1), "HEL")
        self.assertEqual(apply_staggered_text("HELLO", "off", 0, 0, 1), "HELLO")

    def test_effect_keyframes_generate_deterministic_emphasis(self):
        layer = TextLayer("effects")
        layer.keyframes = [TextKeyframe(frame=0, x=0.5, y=0.5, font_size=40, rotation=0.0)]

        bounce = build_effect_keyframes(layer, "Bounce", start_frame=0, frame_count=5)
        self.assertEqual((bounce[0].x, bounce[0].y), (0.5, 0.5))
        self.assertEqual((bounce[-1].x, bounce[-1].y), (0.5, 0.5))
        self.assertLess(bounce[2].y, 0.5)
        self.assertGreater(bounce[2].font_size, 40)

        wiggle = build_effect_keyframes(layer, "Wiggle", start_frame=0, frame_count=6)
        self.assertAlmostEqual(wiggle[0].rotation, 0.0)
        self.assertTrue(any(abs(kf.rotation) > 1.0 for kf in wiggle[1:-1]))

        shake = build_effect_keyframes(layer, "Shake", start_frame=0, frame_count=5)
        self.assertEqual((shake[0].x, shake[0].y, shake[0].rotation), (0.5, 0.5, 0.0))
        self.assertEqual((shake[-1].x, shake[-1].y, shake[-1].rotation), (0.5, 0.5, 0.0))
        self.assertTrue(any((kf.x, kf.y) != (0.5, 0.5) for kf in shake[1:-1]))


class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_recorder_writes_timestamped_error_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = DiagnosticsRecorder(tmp)

            line = recorder.record("error", "Load GIF", "decode failed", path="bad.gif")

            self.assertIn("ERROR", line)
            self.assertIn("Load GIF", line)
            self.assertIn("bad.gif", line)
            self.assertTrue(recorder.log_path.exists())
            contents = recorder.log_path.read_text(encoding="utf-8")
            self.assertIn("decode failed", contents)

    def test_app_error_updates_panel_status_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            window = GifTextApp()
            window.diagnostics = DiagnosticsRecorder(tmp)

            window._show_error("Export", "write denied", path="out.gif", dialog=False)

            self.assertIn("Export", window.diagnostics_view.toPlainText())
            self.assertIn("out.gif", window.diagnostics_view.toPlainText())
            self.assertIn("write denied", window.statusBar().currentMessage())
            self.assertTrue(window.diagnostics.log_path.exists())
            window.close()


class ProjectValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _valid_project(self):
        layer = TextLayer("valid")
        layer.frame_out = 1
        layer.keyframes = [
            TextKeyframe(frame=0, x=0.25, y=0.5, opacity=1.0),
            TextKeyframe(frame=1, x=0.75, y=0.5, opacity=0.6),
        ]
        return {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "version": VERSION,
            "gif_path": "clip.gif",
            "gif_relpath": "clip.gif",
            "layers": [layer.to_dict()],
        }

    def test_project_schema_accepts_current_valid_payload(self):
        validate_project_payload(self._valid_project(), total_frames=2)

    def test_project_schema_rejects_future_version(self):
        project = self._valid_project()
        project["schema_version"] = PROJECT_SCHEMA_VERSION + 1

        with self.assertRaisesRegex(ProjectValidationError, "newer"):
            validate_project_payload(project, total_frames=2)

    def test_project_schema_rejects_invalid_keyframe_bounds(self):
        project = self._valid_project()
        project["layers"][0]["keyframes"][0]["opacity"] = 1.5

        with self.assertRaisesRegex(ProjectValidationError, "opacity"):
            validate_project_payload(project, total_frames=2)

    def test_invalid_project_does_not_mutate_current_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            window = GifTextApp()
            existing = TextLayer("current")
            window.layers = [existing]
            window.gif_path = "current.gif"
            window.diagnostics = DiagnosticsRecorder(tmp)
            project = self._valid_project()
            project["layers"][0]["frame_out"] = 99
            window.pending_project_payload = project
            data = {
                "path": "bad-project.gif",
                "width": 8,
                "height": 8,
                "pil_frames": [Image.new("RGBA", (8, 8)), Image.new("RGBA", (8, 8))],
                "frame_bytes": [b"", b""],
                "durations": [40, 40],
            }

            window._on_gif_loaded(data)

            self.assertEqual(window.layers, [existing])
            self.assertEqual(window.gif_path, "current.gif")
            self.assertIn("frame_out", window.diagnostics_view.toPlainText())
            window.close()


class SubtitleImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_parse_srt_and_vtt_cues(self):
        srt = """1
00:00:00,000 --> 00:00:01,200
First line

2
00:00:01,200 --> 00:00:02,000
Second
line
"""
        vtt = """WEBVTT

00:00:00.500 --> 00:00:01.500
Web cue
"""

        srt_entries = parse_subtitle_text(srt)
        vtt_entries = parse_subtitle_text(vtt)

        self.assertEqual(srt_entries[0], (0.0, 1.2, "First line"))
        self.assertEqual(srt_entries[1], (1.2, 2.0, "Second\nline"))
        self.assertEqual(vtt_entries, [(0.5, 1.5, "Web cue")])

    def test_subtitle_entries_create_timed_layers(self):
        entries = [(0.0, 0.1, "A"), (0.1, 0.3, "B")]
        layers = subtitle_entries_to_layers(entries, [100, 100, 100], 3)

        self.assertEqual([layer.text for layer in layers], ["A", "B"])
        self.assertEqual((layers[0].frame_in, layers[0].frame_out), (0, 1))
        self.assertEqual((layers[1].frame_in, layers[1].frame_out), (1, 2))
        self.assertFalse(layers[0].uppercase)
        self.assertTrue(layers[0].bg_box)
        self.assertEqual(layers[0].keyframes[0].frame, 0)

    def test_app_import_subtitle_file_adds_editable_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "captions.srt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("1\n00:00:00,000 --> 00:00:00,200\nHello\n")
            window = GifTextApp()
            window.gif_pil_frames = [Image.new("RGBA", (8, 8)), Image.new("RGBA", (8, 8))]
            window.frame_durations = [100, 100]
            window.total_frames = 2

            window._import_subtitle_file(path)

            self.assertEqual(len(window.layers), 1)
            self.assertEqual(window.layers[0].text, "Hello")
            self.assertEqual(window.layers[0].frame_out, 1)
            self.assertEqual(window.selected_layer, window.layers[0])
            window.close()


class PathAnimationAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_finish_path_capture_generates_editable_layer_keyframes(self):
        window = GifTextApp()
        frames = [QPixmap(16, 16) for _ in range(5)]
        layer = TextLayer("app path")
        window.gif_frames = frames
        window.total_frames = len(frames)
        window.current_frame = 1
        window.layers = [layer]
        window.selected_layer = layer
        window.path_capture_layer_id = layer.id
        window.spin_path_span.setValue(3)

        window._finish_path_capture([(0.1, 0.1), (0.2, 0.0), (0.8, 1.0), (0.9, 0.9)])

        self.assertEqual(layer.path_start_frame, 1)
        self.assertEqual(layer.path_end_frame, 3)
        self.assertEqual([kf.frame for kf in sorted(layer.keyframes, key=lambda k: k.frame)], [0, 1, 2, 3])
        self.assertEqual((layer.get_keyframe_at(1).x, layer.get_keyframe_at(1).y), (0.1, 0.1))
        self.assertEqual((layer.get_keyframe_at(3).x, layer.get_keyframe_at(3).y), (0.9, 0.9))
        window.close()

    def test_effect_button_flow_generates_keyframes(self):
        window = GifTextApp()
        layer = TextLayer("app effect")
        window.gif_frames = [QPixmap(16, 16) for _ in range(4)]
        window.total_frames = 4
        window.current_frame = 0
        window.layers = [layer]
        window.selected_layer = layer
        window.spin_path_span.setValue(4)

        window._apply_effect_preset("Bounce")

        self.assertEqual([kf.frame for kf in sorted(layer.keyframes, key=lambda k: k.frame)], [0, 1, 2, 3])
        self.assertLess(layer.get_keyframe_at(1).y, 0.5)
        self.assertEqual(layer.get_keyframe_at(3).y, 0.5)
        window.close()

    def test_easing_selector_updates_current_keyframe(self):
        window = GifTextApp()
        layer = TextLayer("app ease")
        window.layers = [layer]
        window.selected_layer = layer
        idx = window.ease_combo.findData("ease_out")
        window.ease_combo.setCurrentIndex(idx)

        self.assertEqual(layer.get_keyframe_at(0).easing, "ease_out")
        window.close()

    def test_stagger_controls_update_selected_layer(self):
        window = GifTextApp()
        layer = TextLayer("app stagger")
        window.layers = [layer]
        window.selected_layer = layer
        window.stagger_combo.setCurrentIndex(window.stagger_combo.findData("letters"))
        window.spin_stagger_frames.setValue(4)

        self.assertEqual(layer.stagger_mode, "letters")
        self.assertEqual(layer.stagger_frames, 4)
        window.close()

    def test_stroke_shadow_controls_update_current_keyframe(self):
        window = GifTextApp()
        layer = TextLayer("app render fields")
        window.layers = [layer]
        window.selected_layer = layer
        window.spin_outline_opacity.setValue(0.45)
        window.spin_shadow_opacity.setValue(0.25)

        self.assertAlmostEqual(layer.get_keyframe_at(0).outline_opacity, 0.45)
        self.assertAlmostEqual(layer.get_keyframe_at(0).shadow_opacity, 0.25)
        window.close()

    def test_range_apply_delete_and_visibility_tools(self):
        window = GifTextApp()
        layer = TextLayer("range tools")
        window.layers = [layer]
        window.selected_layer = layer
        window.total_frames = 6
        window.current_frame = 0
        layer.keyframes[0].font_size = 42
        window.spin_range_start.setValue(1)
        window.spin_range_end.setValue(3)

        window._apply_current_keyframe_to_range()

        self.assertEqual([kf.frame for kf in sorted(layer.keyframes, key=lambda k: k.frame)], [0, 1, 2, 3])
        self.assertEqual(layer.get_keyframe_at(2).font_size, 42)

        window.spin_range_start.setValue(1)
        window.spin_range_end.setValue(2)
        window._delete_keyframe_range()

        self.assertIsNone(layer.get_keyframe_at(1))
        self.assertIsNone(layer.get_keyframe_at(2))
        self.assertIsNotNone(layer.get_keyframe_at(3))

        window.spin_range_start.setValue(2)
        window.spin_range_end.setValue(4)
        window._set_visibility_to_range()

        self.assertEqual((layer.frame_in, layer.frame_out), (2, 4))
        window.close()

    def test_range_copy_and_paste_tools_preserve_offsets(self):
        window = GifTextApp()
        layer = TextLayer("copy range")
        layer.keyframes = [
            TextKeyframe(frame=1, x=0.2, font_size=20),
            TextKeyframe(frame=3, x=0.6, font_size=36),
        ]
        window.layers = [layer]
        window.selected_layer = layer
        window.total_frames = 8
        window.spin_range_start.setValue(1)
        window.spin_range_end.setValue(3)

        window._copy_keyframes_in_range()
        window.spin_range_start.setValue(4)
        window.spin_range_end.setValue(6)
        window._paste_keyframe_range()

        self.assertEqual(layer.get_keyframe_at(4).font_size, 20)
        self.assertEqual(layer.get_keyframe_at(6).font_size, 36)
        self.assertAlmostEqual(layer.get_keyframe_at(6).x, 0.6)
        window.close()


class WorkerTests(unittest.TestCase):
    def _text_layer(self):
        layer = TextLayer("Hi")
        layer.uppercase = False
        layer.keyframes[0].x = 0.5
        layer.keyframes[0].y = 0.5
        layer.keyframes[0].font_size = 24
        layer.keyframes[0].color = "#ffffff"
        layer.keyframes[0].outline_width = 0
        layer.shadow = False
        return layer

    def _has_rendered_text(self, image):
        frame = image.convert("RGB")
        return any(r > 180 and g > 180 and b > 180 for r, g, b in frame.getdata())

    def test_load_worker_decodes_generated_gif(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tiny.gif")
            frames = [
                Image.new("RGBA", (8, 8), (255, 0, 0, 255)),
                Image.new("RGBA", (8, 8), (0, 255, 0, 255)),
            ]
            frames[0].save(path, save_all=True, append_images=frames[1:], duration=[40, 60], loop=0)
            worker = LoadGifWorker(path)
            results = []
            failures = []
            worker.finished.connect(results.append)
            worker.failed.connect(failures.append)

            worker.run()

            self.assertEqual(failures, [])
            self.assertEqual(results[0]["width"], 8)
            self.assertEqual(len(results[0]["pil_frames"]), 2)
            self.assertEqual(len(results[0]["frame_bytes"]), 2)

    def test_export_worker_writes_gif_without_mutating_layer_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "out.gif")
            frame = Image.new("RGBA", (48, 32), (10, 10, 10, 255))
            layer = TextLayer("worker")
            layer.keyframes[0].x = 0.5
            layer.keyframes[0].y = 0.5
            before_counter = TextLayer._counter
            worker = ExportWorker([frame, frame], [layer.to_dict()], [30, 30], 2, output, ".gif")
            results = []
            failures = []
            worker.finished.connect(results.append)
            worker.failed.connect(failures.append)

            worker.run()

            self.assertEqual(failures, [])
            self.assertTrue(os.path.exists(output))
            self.assertEqual(results, [output])
            self.assertEqual(TextLayer._counter, before_counter)

    def test_export_worker_preserves_gif_frames_duration_and_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "out.gif")
            frames = [
                Image.new("RGBA", (80, 48), (0, 0, 0, 255)),
                Image.new("RGBA", (80, 48), (4, 0, 0, 255)),
            ]
            worker = ExportWorker(frames, [self._text_layer().to_dict()], [40, 80], 2, output, ".gif")
            failures = []
            worker.failed.connect(failures.append)

            worker.run()

            self.assertEqual(failures, [])
            with Image.open(output) as exported:
                self.assertEqual(exported.n_frames, 2)
                durations = []
                rendered = []
                for frame_index in range(exported.n_frames):
                    exported.seek(frame_index)
                    durations.append(exported.info.get("duration"))
                    rendered.append(self._has_rendered_text(exported))
                self.assertEqual(durations, [40, 80])
                self.assertEqual(rendered, [True, True])

    def test_export_worker_writes_webp_and_png_sequence_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            frames = [
                Image.new("RGBA", (80, 48), (0, 0, 0, 255)),
                Image.new("RGBA", (80, 48), (4, 0, 0, 255)),
            ]
            layer_payload = [self._text_layer().to_dict()]
            webp_output = os.path.join(tmp, "out.webp")
            png_output = os.path.join(tmp, "seq.png")

            webp_worker = ExportWorker(frames, layer_payload, [50, 70], 2, webp_output, ".webp")
            png_worker = ExportWorker(frames, layer_payload, [50, 70], 2, png_output, ".png")
            failures = []
            webp_worker.failed.connect(failures.append)
            png_worker.failed.connect(failures.append)

            webp_worker.run()
            png_worker.run()

            self.assertEqual(failures, [])
            with Image.open(webp_output) as exported_webp:
                self.assertEqual(exported_webp.n_frames, 2)
            first_png = os.path.join(tmp, "seq_0000.png")
            second_png = os.path.join(tmp, "seq_0001.png")
            self.assertTrue(os.path.exists(first_png))
            self.assertTrue(os.path.exists(second_png))
            with Image.open(first_png) as first, Image.open(second_png) as second:
                self.assertTrue(self._has_rendered_text(first))
                self.assertTrue(self._has_rendered_text(second))

    def test_project_payload_round_trips_layer_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            gif_path = os.path.join(tmp, "clip.gif")
            project_path = os.path.join(tmp, "clip.giftext")
            layer = self._text_layer()
            layer.frame_out = 1
            layer.stagger_mode = "letters"
            layer.stagger_frames = 2

            payload = build_project_payload(gif_path, [layer], project_path)
            validate_project_payload(payload, total_frames=2)
            restored = TextLayer.from_dict(payload["layers"][0])

            self.assertEqual(payload["schema_version"], PROJECT_SCHEMA_VERSION)
            self.assertEqual(payload["gif_relpath"], "clip.gif")
            self.assertEqual(restored.text, layer.text)
            self.assertEqual(restored.frame_out, 1)
            self.assertEqual(restored.stagger_mode, "letters")
            self.assertEqual(restored.keyframes[0].font_size, 24)

    def test_corrupt_project_payload_is_rejected(self):
        with self.assertRaisesRegex(ProjectValidationError, "layers"):
            validate_project_payload({"schema_version": PROJECT_SCHEMA_VERSION, "layers": "bad"}, total_frames=2)

    def test_shared_renderer_draws_text(self):
        frame = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
        layer = TextLayer("Hi")

        rendered = render_text_pil(frame, layer, 0, 1)

        self.assertIsNot(rendered, frame)
        self.assertGreater(rendered.getbbox()[2], 0)

    @unittest.skipUnless(HAS_IMAGEIO, "imageio not installed")
    def test_export_worker_writes_mp4_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "out.mp4")
            frames = [
                Image.new("RGBA", (64, 48), (0, 0, 0, 255)),
                Image.new("RGBA", (64, 48), (50, 0, 0, 255)),
            ]
            layer = self._text_layer()
            worker = ExportWorker(frames, [layer.to_dict()], [100, 100], 2, output, ".mp4")
            results = []
            failures = []
            worker.finished.connect(results.append)
            worker.failed.connect(failures.append)

            worker.run()

            self.assertEqual(failures, [])
            self.assertTrue(os.path.exists(output))
            self.assertGreater(os.path.getsize(output), 0)

    def test_unicode_text_uses_export_font_fallback(self):
        frame = Image.new("RGBA", (220, 80), (0, 0, 0, 0))
        layer = TextLayer("مرحبا 안녕 नमस्ते")
        layer.uppercase = False
        layer.keyframes[0].font_size = 28

        font = get_pil_font(layer, 28, layer.text)
        rendered = render_text_pil(frame, layer, 0, 1)

        self.assertIsNotNone(font)
        self.assertIsNotNone(rendered.getbbox())


class AccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_controls_have_accessible_names(self):
        window = GifTextApp()
        controls = [
            window.btn_load, window.btn_export, window.btn_save_proj,
            window.btn_undo, window.btn_redo, window.btn_play,
            window.btn_prev, window.btn_next, window.btn_add,
            window.frame_slider, window.txt_input, window.font_combo,
            window.spin_size, window.spin_opacity, window.spin_rotation,
            window.ease_combo, window.btn_color, window.btn_outline_color,
            window.btn_set_kf, window.btn_del_kf, window.canvas,
            window.layer_timeline, window.diagnostics_view,
        ]
        for ctrl in controls:
            self.assertTrue(
                ctrl.accessibleName(),
                f"{ctrl.__class__.__name__} (objectName={ctrl.objectName()!r}) missing accessible name",
            )
        window.close()

    def test_canvas_and_timeline_accept_focus(self):
        window = GifTextApp()
        self.assertNotEqual(window.canvas.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertNotEqual(window.layer_timeline.focusPolicy(), Qt.FocusPolicy.NoFocus)
        window.close()


class DiagnosticsBundleTests(unittest.TestCase):
    def test_bundle_includes_version_and_environment(self):
        bundle = build_diagnostics_bundle("1.5.0", gif_path="test.gif", total_frames=10, layer_count=2)
        self.assertIn("GifText v1.5.0", bundle)
        self.assertIn("Python:", bundle)
        self.assertIn("PyQt6:", bundle)
        self.assertIn("Pillow:", bundle)
        self.assertIn("test.gif", bundle)
        self.assertIn("Frames: 10", bundle)
        self.assertIn("Layers: 2", bundle)

    def test_bundle_includes_recent_log_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = DiagnosticsRecorder(tmp)
            recorder.record("error", "Export", "write denied")
            bundle = build_diagnostics_bundle("1.5.0", log_dir=tmp)
            self.assertIn("write denied", bundle)

    def test_bundle_handles_missing_log_dir(self):
        bundle = build_diagnostics_bundle("1.5.0", log_dir="/nonexistent/path")
        self.assertIn("does not exist", bundle)


class CLIRenderTests(unittest.TestCase):
    def test_cli_render_produces_gif_from_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            gif_path = os.path.join(tmp, "source.gif")
            frames = [
                Image.new("RGBA", (32, 24), (255, 0, 0, 255)),
                Image.new("RGBA", (32, 24), (0, 255, 0, 255)),
            ]
            frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                           duration=[50, 50], loop=0)
            layer = TextLayer("Hello")
            layer.frame_out = 1
            payload = build_project_payload(gif_path, [layer])
            project_path = os.path.join(tmp, "test.giftext")
            import json
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)

            output_path = os.path.join(tmp, "output.gif")
            result = cli_render(project_path, output_path)

            self.assertEqual(result, 0)
            self.assertTrue(os.path.exists(output_path))
            with Image.open(output_path) as out:
                self.assertEqual(out.n_frames, 2)

    def test_cli_render_returns_error_for_missing_project(self):
        result = cli_render("/nonexistent/project.giftext", "output.gif")
        self.assertEqual(result, 1)


class VideoImportTests(unittest.TestCase):
    def _make_test_video(self, tmp_dir, duration_frames=30, fps=10, width=64, height=48):
        if not HAS_IMAGEIO:
            return None
        import av
        path = os.path.join(tmp_dir, "test.mp4")
        container = av.open(path, mode="w")
        stream = container.add_stream("mpeg4", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        for i in range(duration_frames):
            r = int(255 * i / duration_frames)
            arr = np.full((height, width, 3), [r, 50, 100], dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        container.close()
        return path

    @unittest.skipUnless(HAS_IMAGEIO, "imageio not installed")
    def test_video_metadata_returns_fps_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._make_test_video(tmp, duration_frames=20, fps=10)
            meta = get_video_metadata(path)
            self.assertIsNotNone(meta)
            self.assertAlmostEqual(meta["fps"], 10, delta=1)
            self.assertGreater(meta["duration"], 0)

    @unittest.skipUnless(HAS_IMAGEIO, "imageio not installed")
    def test_video_worker_reads_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._make_test_video(tmp, duration_frames=20, fps=10)
            worker = LoadVideoWorker(path, target_fps=5, max_frames=100)
            results = []
            failures = []
            worker.finished.connect(results.append)
            worker.failed.connect(failures.append)

            worker.run()

            self.assertEqual(failures, [])
            self.assertEqual(len(results), 1)
            data = results[0]
            self.assertGreaterEqual(len(data["pil_frames"]), 2)
            self.assertEqual(data["width"], 64)
            self.assertEqual(data["height"], 48)
            self.assertEqual(len(data["durations"]), len(data["pil_frames"]))

    @unittest.skipUnless(HAS_IMAGEIO, "imageio not installed")
    def test_video_worker_respects_max_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._make_test_video(tmp, duration_frames=50, fps=10)
            worker = LoadVideoWorker(path, target_fps=10, max_frames=5)
            results = []
            worker.finished.connect(results.append)
            worker.failed.connect(lambda _: None)

            worker.run()

            self.assertEqual(len(results[0]["pil_frames"]), 5)

    @unittest.skipUnless(HAS_IMAGEIO, "imageio not installed")
    def test_video_worker_resizes_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._make_test_video(tmp, duration_frames=10, fps=5, width=200, height=150)
            worker = LoadVideoWorker(path, target_fps=5, max_frames=100, max_size=80)
            results = []
            worker.finished.connect(results.append)
            worker.failed.connect(lambda _: None)

            worker.run()

            data = results[0]
            self.assertLessEqual(data["width"], 80)
            self.assertLessEqual(data["height"], 80)

    def test_video_extensions_include_common_formats(self):
        for ext in [".mp4", ".webm", ".avi", ".mov"]:
            self.assertIn(ext, VIDEO_EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
