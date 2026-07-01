# Changelog

All notable changes to GifText will be documented in this file.

## [v1.5.0] - 2026-07-01

- Added `build_release.py` release build script with SHA-256 checksum generation and smoke test.
- Added optional `--sign` flag for code signing with a certificate when available.
- Added video import support via imageio-ffmpeg for short clips (MP4, WebM, AVI, MOV).
- Added in-app diagnostics bundle export with version, dependency, OS, and log details.
- Added MP4 and WebM video export via PyAV alongside existing GIF/WebP/PNG formats.
- Added `--render` CLI mode for headless project rendering to GIF/WebP/PNG/MP4/WebM.
- Added Trim Frames and Resize Source controls for editing loaded frames before labeling.
- Refactored single-file app into modules: models, animation, rendering, project, diagnostics, workers.

## [v1.4.2] - 2026-06-28

- Added export-side Unicode font fallback candidates for non-Latin captions.
- Passed rendered caption text into the PIL font resolver so fallback selection can respond to script coverage needs.
- Added multilingual render regression coverage.

## [v1.4.1] - 2026-06-28

- Added range tools for applying the current keyframe, copying/pasting keyframes with offsets, deleting keyframes, and setting layer visibility across a selected frame range.
- Preserved the existing Repeat 10 Frames action as a separate quick keyframe operation.
- Added app-level regression tests for range apply/delete/visibility and copy/paste behavior.

## [v1.4.0] - 2026-06-28

- Added SRT/VTT subtitle import that creates timed editable text layers.
- Added subtitle parser and frame-mapping tests for multi-line SRT and WebVTT cues.
- Added an app-level subtitle import test using generated fixtures.

## [v1.3.9] - 2026-06-28

- Added generated-fixture regression tests for GIF duration/frame preservation, WebP frame export, PNG sequence export, and text rendering across multiple exported frames.
- Added a project payload builder and round-trip coverage for `.giftext` layer state.
- Added explicit corrupt project payload rejection coverage.

## [v1.3.8] - 2026-06-28

- Added `.giftext` project `schema_version` writes for new saves.
- Added project validation for schema version, path fields, layer timing, path points, color fields, opacity bounds, easing, and keyframe frame ranges.
- Prevented invalid project payloads from mutating the current document after the referenced GIF decodes.

## [v1.3.7] - 2026-06-28

- Added structured diagnostics for GIF load, project save/load, recent-file, tracking, and export failures.
- Added a right-side Diagnostics panel plus timestamped error logs under `%USERPROFILE%\.giftext\logs\`.
- Added diagnostics regression coverage for log writing and app-level panel/status updates.

## [v1.3.6] - 2026-06-28

- Moved GIF loading, forward tracking, and export rendering/saving into cancellable `QThread` workers with progress status messages.
- Added a Cancel Work control and removed the export-time `QApplication.processEvents()` responsiveness workaround.
- Added worker regression coverage for generated GIF loading, export writing, and shared PIL text rendering.

## [v1.3.5] - 2026-06-27

- Added separate stroke opacity, shadow color, and shadow opacity controls for animated text keyframes.
- Applied independent stroke/shadow styling consistently in canvas preview and exported frames.

## [v1.3.4] - 2026-06-27

- Added staggered text reveal controls for lines, words, and letters with configurable frame step timing.
- Applied staggered reveal consistently in canvas preview and exported GIF/WebP/PNG frames.

## [v1.3.3] - 2026-06-27

- Added per-keyframe cubic Bezier easing with Linear, Ease In, Ease Out, Ease In Out, Snappy, and Overshoot curve choices.
- Replaced fixed smoothstep interpolation with the selected outgoing keyframe curve and added serialization/test coverage.

## [v1.3.2] - 2026-06-27

- Added Bounce, Wiggle, and Shake motion preset buttons that generate editable emphasis keyframes over the selected motion span.
- Extended path animation tests with deterministic effect-helper coverage and an offscreen app-level effect flow.

## [v1.3.1] - 2026-06-27

- Added Bezier path animation for text layers: Draw Path captures four canvas points, generates editable per-frame position keyframes over the selected span, and saves the path guide in `.giftext` projects.
- Added unit coverage for path sampling, generated keyframes, path metadata serialization, and the offscreen window-level path completion flow.

## [v1.3.0] - 2026-06-27

- Added OpenCV forward motion tracking for selected layers, with CSRT/KCF tracker support when available and Lucas-Kanade optical-flow fallback.
- Added explicit `requirements.txt` dependency setup and PyInstaller-safe multiprocessing guard.
- Added pinned PyInstaller build requirements, runtime hook, spec file, and Windows exe build instructions.

## [v1.2.1] - 2026-06-26

- v1.2.1: UI color refinement, toolbar layout restructure
- v1.2.0: Deep dark UI overhaul, layer visibility, helper refactors
- v1.1.0: Drag-resize, recent files menu, undo-on-drag, README
- v1.0.0: Major feature release - 16 features from competitive research
- v0.2.0: On-canvas text selection, drag tracking, mousewheel frame stepping
- Initial commit: GifText v0.1.0 - animated GIF text editor
