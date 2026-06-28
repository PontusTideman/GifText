# ROADMAP

Backlog for GifText. Stays focused on the "label moving subjects in a GIF" niche that nothing
else handles cleanly on desktop.

## Planned Features

### Text rendering
- **Gradient fill** + **rainbow animation** on the text color channel.
- **Font import** - load any TTF/OTF from disk; font picker with search.
- **Emoji rendering** via the OS emoji font with color support.
- **Rich text per-line** - different size/color/weight within one text block.
- **Curved / arc text** path option.

### Canvas
- **Multi-layer stickers / emoji / shapes** alongside text layers with the same keyframe engine.
- **Mask layer** - drawable alpha mask that clips text to a subject shape.
- **Crop / rotate source GIF** non-destructively at export.
- **Trim range** - cut start/end frames before labeling.
- **Resize source** for smaller output files.

### Export
- **Animated WebP + APNG** in addition to GIF and PNG sequence.
- **MP4 / WebM** export via PyAV so users can post to platforms that don't accept GIF.
- **Size-target export** - iteratively re-encode until output <= N MB.
- **Per-frame delay override** on export.
- **Palette quality slider** (gif.js-style dither options).

### Workflow
- **Import GifStudio project file** (sibling browser app) and reverse - unify the keyframe model
  across both apps.
- **Project template library** - save a multi-layer setup as a template, apply to a new GIF.
- **Recent projects with thumbnails**.
- **Autosave to IDB-like local cache** every N seconds.
- **Session recovery** on crash.

### Distribution
- **macOS `.app`** via py2app, notarized.
- **Linux AppImage**.

## Competitive Research

- **Ezgif "Add text" tool** - single-frame or globally-fixed text; no tracking. GifText's
  keyframes are already the differentiator; keep pushing on that axis.
- **Kapwing / Giphy Caption** - polished but server-side and watermarked on free tier. GifText
  is the local-only alternative.
- **After Effects** - overkill for GIF-labeling; GifText stays the one-purpose fast option.
- **ScreenToGif (C#, Windows)** - excellent frame-editor; worth borrowing its frame-level
  operations (delete, duplicate, reverse range) which GifText currently lacks.
- **Motion Canvas / Rive** - code-based animation; useful as a reference for the keyframe curve
  editor.

## Nice-to-Haves

- **Auto-suggest label position** - detect subjects via BlazeFace/MediaPipe and propose where to
  anchor a label.
- **Speech-to-text auto-subtitle** via Whisper (small model) on the GIF's audio if source video
  file is supplied alongside.
- **Share-to-imgur / giphy** button with user-supplied API token.
- **Cloud sync of projects** (opt-in, user-owned S3 bucket).
- **Plugin SDK** (Python entry points) for custom effect layers.
- **Command-line mode** - headless render from a project file, for batch labeling pipelines.

## Open-Source Research (Round 2)

### Related OSS Projects
- **animeme (OfirKP)** - https://github.com/OfirKP/animeme - Closest peer: Python GIF-meme editor with keyframes for text position + font size, linear interpolation, JSON template save/load, CLI `generate_meme.py`.
- **Gifcurry** - https://github.com/lettier/gifcurry - Haskell; GUI+CLI with font/size/color/position/outline/rotation + per-text timing. Mature text overlay model.
- **Kapi** - https://github.com/jeremyckahn/kapi - Pure keyframe animation API for canvas; useful library model if you refactor animation engine.
- **rekapi** - https://github.com/jeremyckahn/rekapi - Kapi's successor; full tween engine with easing functions and actor-based timeline.
- **ScreenToGif** - https://github.com/NickeManarin/ScreenToGif - C#/WPF per-frame text edit; different UX paradigm (no interpolation) but strong frame-list ergonomics.
- **gif-meme-generator / impactful JS libs** - https://github.com/topics/gif-maker - small one-off meme scripts worth skimming.
- **gif.js** - https://github.com/jnordberg/gif.js - Encoder if you want a web-export path in the future.

### Features to Borrow
- JSON template save/load from `animeme` - already present but extend: export `.gmtext` templates to share online, import via drag-drop.
- Keyframe interpolation of font size + rotation + color (`animeme` position-only + `rekapi`) - expand beyond position; opacity fade for meme transitions.
- Easing curves (`rekapi`) - ease-in/out/back/bounce; current linear only is limiting.
- Subtitle import `.srt`/`.vtt` (`Gifcurry`) - auto-generate timed text tracks from caption files.
- CLI rendering (`animeme generate_meme.py`) - headless `python gif_text.py --template=x.json --text="HELLO" --out=out.gif`.
- Font outline + drop-shadow (`Gifcurry`) - "Impact white on black stroke" is 90% of memes; preset button.
- Multi-text-layer timeline (each text its own track) - `ScreenToGif` frame-list + per-layer enable/disable.

### Patterns & Architectures Worth Studying
- **Actor + timeline model** (`rekapi`): text = actor; keyframes = state at time t; engine tweens. Cleaner than per-frame dict lookup; supports easing + pause/resume.
- **Dirty-rect repaint**: only re-rasterize the text area on keyframe change, not the whole GIF. Matters once you have 5+ text layers on 200-frame GIFs.
- **Bezier timing functions** (cubic-bezier) like CSS - store 4 control points, evaluate per-frame. Tiny code, huge UX gain vs linear.
- **Template versioning**: animeme's JSON is flat; add `{"schema_version": 2, ...}` now so future fields (opacity, rotation, outline) don't break old templates.

## Research-Driven Additions

- [ ] P0 - Move load, tracking, and export into cancellable worker threads
  Why: Large GIF decode/render/OpenCV work currently runs on the GUI thread and can freeze the editor.
  Evidence: `GifText.py:2200`, `GifText.py:2817`, `GifText.py:3090`; ScreenToGif background export model.
  Touches: `GifText.py`, new worker module if the file is split, `test_giftext.py`
  Acceptance: Loading, tracking, and export show progress, stay responsive, support cancel, and never call `QApplication.processEvents()` as the main responsiveness mechanism.
  Complexity: L

- [ ] P0 - Add structured diagnostics for load, project, recent-file, tracking, and export failures
  Why: Current failures are status-bar-only, and recent-file persistence can fail silently.
  Evidence: `GifText.py:2252`, `GifText.py:3058`, `GifText.py:3080`, `GifText.py:3138`.
  Touches: `GifText.py`, diagnostics/logging module, README troubleshooting section
  Acceptance: Exceptions produce a timestamped crash/error log, an in-app log panel entry, and a user-visible recovery message with the failed path/action.
  Complexity: M

- [ ] P0 - Version and validate `.giftext` project schema before applying state
  Why: Project files accept broad unvalidated JSON and have no migration path beyond the app version string.
  Evidence: `GifText.py:672`, `GifText.py:688`, `GifText.py:3017`; Rekapi actor/keyframe model; Web Animations keyframe format.
  Touches: `GifText.py`, project I/O module, `test_giftext.py`
  Acceptance: Project load validates schema version, paths, frame ranges, colors, opacity bounds, keyframe fields, and reports actionable errors without mutating the current document on failure.
  Complexity: M

- [ ] P0 - Add export and project round-trip regression tests with tiny generated GIF fixtures
  Why: Tests cover helper logic but not the workflows most likely to corrupt user output.
  Evidence: `test_giftext.py`; Pillow GIF save behavior; GifText export code in `GifText.py:3090`.
  Touches: `test_giftext.py`, export/project helpers after extraction
  Acceptance: Tests verify GIF/WebP/PNG sequence frame count, duration preservation, text rendering on multiple frames, project save/load parity, and corrupt project rejection.
  Complexity: M

- [ ] P1 - Import SRT/VTT subtitle tracks as timed text layers
  Why: Gifcurry and commercial editors treat subtitle import as a core caption workflow, while GifText already has layer timing and text reveal primitives.
  Evidence: Gifcurry subtitle import; VEED subtitle workflow; `TextLayer.frame_in/frame_out` in `GifText.py:576`.
  Touches: `GifText.py`, subtitle parser module, `test_giftext.py`
  Acceptance: Importing `.srt` or `.vtt` creates editable layers with frame-aligned in/out timing and preserves multi-line captions.
  Complexity: M

- [ ] P1 - Add range-based keyframe and text-annotation operations
  Why: Ezgif supports per-text frame ranges and ScreenToGif users value changing timing across frame ranges; GifText only has manual keyframes and a fixed "Repeat 10 Frames" action.
  Evidence: Ezgif frame-range annotations; ScreenToGif timing/range editing; `GifText.py:2714`.
  Touches: `GifText.py`, `LayerTimeline`, `TextLayer`, `test_giftext.py`
  Acceptance: Users can choose a frame range, apply/copy/delete selected layer keyframes in that range, and set text visibility timing from the range selection.
  Complexity: M

- [ ] P1 - Add Unicode font fallback and script coverage for preview/export parity
  Why: Ezgif advertises full Unicode plus Arabic, Korean, Hebrew, Thai, Tamil, Telugu, and Devanagari fonts; GifText export currently probes Windows font filenames directly.
  Evidence: Ezgif font coverage; `GifText.py:3222`.
  Touches: `GifText.py`, font resolver module, `test_giftext.py`, README
  Acceptance: Non-Latin sample captions render in preview and export with matching glyph coverage or a clear missing-font warning.
  Complexity: M

- [ ] P1 - Add video input import for short clips while preserving the GIF-labeling workflow
  Why: GIPHY, Kapwing, Gifcurry, and ScreenToGif all accept video sources; GifText currently starts only from animated GIF files.
  Evidence: GIPHY GIF Maker video/YouTube intake; Kapwing GIF maker; Gifcurry video-to-GIF workflow.
  Touches: `GifText.py`, input/import module, optional FFmpeg/PyAV dependency decision, README
  Acceptance: Importing a supported short video lets the user trim/select FPS/size, then continues into the existing frame/keyframe editor.
  Complexity: L

- [ ] P1 - Ship signed, checksummed Windows release artifacts with a local smoke test
  Why: The PyInstaller spec builds an exe but has no signing/checksum/release verification flow.
  Evidence: `GifText.spec`; PyInstaller 6.21.0 changelog and multiprocessing guidance; current `dist/` artifact.
  Touches: `GifText.spec`, release script, README, CHANGELOG
  Acceptance: A clean local build produces `GifText.exe`, checksum file, smoke-test result, and signing when a certificate is available.
  Complexity: M

- [ ] P2 - Add accessibility and focus-order QA for the editor UI
  Why: The app has a dense inspector and custom canvas/timeline controls but no automated accessibility checks or documented focus behavior.
  Evidence: `GifText.py:1494`, `GifText.py:1639`, `GifText.py:1688`, `GifText.py:1731`.
  Touches: `GifText.py`, UI test harness, README accessibility notes
  Acceptance: Main controls expose accessible names/descriptions, focus order follows the workflow, high-contrast text passes checks, and custom timeline/canvas actions have keyboard-independent button/menu alternatives.
  Complexity: M

- [ ] P2 - Add an in-app diagnostics bundle for support and bug reports
  Why: Community GIF tooling support often hinges on encoder/version/path details, and GifText currently has no way to export environment state.
  Evidence: ScreenToGif encoder configuration issues; `requirements.txt`; `GifText.spec`.
  Touches: diagnostics module, `GifText.py`, README troubleshooting section
  Acceptance: A menu/button exports app version, dependency versions, OS, recent log excerpts, selected project metadata, and export settings without embedding user media frames.
  Complexity: S

- [ ] P2 - Refactor the single-file app behind stable model, render, tracking, project I/O, and worker boundaries
  Why: `GifText.py` mixes every concern in one 3,256-line file, making workerization, schema validation, and export testing harder.
  Evidence: `GifText.py`; Rekapi actor/timeline separation.
  Touches: `GifText.py`, new modules, `test_giftext.py`
  Acceptance: Existing tests pass after extracting pure model/render/project/tracking functions, and UI code calls those boundaries without behavior changes.
  Complexity: L
