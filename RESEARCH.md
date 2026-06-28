# Research - GifText

## Executive Summary
Verified: GifText is a focused PyQt6 desktop editor for adding animated, motion-tracked text to GIFs. Its strongest shape is the local keyframe workflow: on-canvas labels, interpolation, OpenCV tracking, Bezier paths, presets, reveal timing, project save/load, and GIF/WebP/PNG export. The highest-value direction is to make that workflow trustworthy under real creator loads before expanding formats: move long work off the GUI thread, add crash/error recovery, harden project/export validation, and prove export fidelity with tests. Top opportunities: async load/export/tracking; structured diagnostics; `.giftext` schema/version validation; export regression tests; subtitle import; range-based batch editing; Unicode/font fallback parity; video input; signed release artifacts; accessibility/focus polish.

## Product Map
- Core workflows: load an animated GIF, add one text layer per subject, position/keyframe labels, optionally generate tracking/path/effect keyframes, export GIF/WebP/PNG sequence.
- User personas: meme makers labeling moving subjects; documentation creators annotating short loops; creators who want local-only editing instead of hosted/watermarked tools; maintainers building small Windows desktop media tools.
- Platforms and distribution: Python 3.10+ source install and Windows PyInstaller exe via `GifText.spec`; planned macOS/Linux packaging already exists in `ROADMAP.md`.
- Key integrations and data flows: Pillow loads/renders frames; PyQt6 previews and edits; OpenCV tracks label seed points; `.giftext` stores source GIF path plus serialized layers; PyInstaller bundles `icon.png` with `runtime_hook_mp.py`.

## Competitive Landscape
- Ezgif: does frame-range text, multi-format animated inputs, Unicode font coverage, and no-watermark web workflows well. Learn from its per-annotation frame ranges, broad script font support, and APNG/WebP/AVIF/JXL input posture; avoid its server-upload privacy tradeoff.
- ScreenToGif: does frame-list editing, encoder choice, timing/range changes, troubleshooting, and Windows distribution well. Borrow background export/cancel/progress, range operations, and encoder diagnostics; avoid becoming a general recorder/editor.
- Gifcurry: covers video-to-GIF import, trim/crop/resize/FPS/color-count/dither, subtitle import, GUI+CLI. Borrow subtitle import and video intake; avoid pulling in a broad video-editor surface before GifText's tracking core is hardened.
- Animeme: closest OSS keyframe text peer, with draggable text keyframes and template generation. GifText is already ahead on tracking/easing/styling; borrow headless/template discipline rather than its simpler interpolation model.
- Kapwing/VEED/Canva/GIPHY: commercial tools win on onboarding, subtitles, stickers, mobile/social sharing, and broad media import. Borrow low-friction input/export flows; avoid cloud accounts, paywalls, collaboration, and watermark economics.
- Rekapi/Web Animations models: actor/keyframe abstractions separate timeline state from rendering. Borrow this boundary if `GifText.py` is split; avoid a wholesale framework port.
- Awesome GIF/FFmpeg ecosystem: community tools repeatedly emphasize compact output, palette quality, gifski/ffmpeg encoders, and video-to-GIF conversion. Existing roadmap already covers size target, palette controls, MP4/WebM export, and CLI, so do not duplicate those.

## Security, Privacy, and Reliability
- Verified: `_load_gif_from_path`, `_track_selected_layer_forward`, and `_export_gif` run frame decode, OpenCV tracking, and full-frame render/export synchronously on the GUI thread (`GifText.py:2200`, `GifText.py:2817`, `GifText.py:3090`). Large GIFs can freeze the app and make cancellation impossible.
- Verified: load/project/export failures are reduced to status-bar text, and recent-file write failures are silently swallowed (`GifText.py:2252`, `GifText.py:3058`, `GifText.py:3080`). There is no log panel, traceback file, or retry/recovery surface.
- Verified: `.giftext` has no schema version/migration guard beyond `"version": VERSION`, and `TextLayer.from_dict` accepts broad unvalidated ranges/fields (`GifText.py:672`, `GifText.py:688`, `GifText.py:3017`). Corrupt project files can produce confusing state or later render errors.
- Verified: Pillow 12.2.0 is current and includes a fix for CVE-2026-42311; dependency pins should stay current because image parsers are security-sensitive.
- Verified: Qt 6.11.1 shipped hundreds of bug/security/quality fixes after 6.11.0; GifText pins PyQt6 6.11.0 in `requirements.txt`.
- Likely: Windows exe builds will trigger reputation warnings until a signed release and checksum flow exists; `GifText.spec` has no `codesign_identity`.

## Architecture Assessment
- Verified: `GifText.py` is 3,256 lines and mixes model, rendering, widgets, tracking, project I/O, recent-file persistence, and export. First split should be `models.py`, `rendering.py`, `tracking.py`, `project_io.py`, and `workers.py` after the async boundary is introduced.
- Verified: tests cover path sampling, effects, easing, stagger, serialization snippets, and offscreen app flows, but not GIF load, `.giftext` project round-trip, export frame count/duration, corrupt input, recent-file persistence, tracking fallback, or PyInstaller smoke (`test_giftext.py`).
- Verified: preview/export parity exists for recent text styling, but the project lacks golden-image export tests, palette/disposal checks, and non-Latin/font-fallback coverage.
- Verified: the UI has one dark theme and no explicit accessibility pass. Controls mostly use visible labels, but focus order, accessible names, high-contrast checks, and screen-reader labels are not tested.
- Likely: an actor/timeline boundary would reduce shared-state coupling, but landing workers and tests first gives better risk reduction.

## Rejected Ideas
- Multi-user collaboration: rejected because the product is a local desktop GIF labeler and commercial cloud tools already own collaborative editing.
- Built-in upload/share to GIPHY/Imgur: rejected for now because local-only privacy is a differentiator; keep user-owned export files first.
- Full mobile app: rejected because the current stack and strongest niche are desktop precise labeling; mobile is better served by GIPHY/Canva-style capture workflows.
- General video editor expansion: rejected as a near-term direction; use video import/export where it supports GIF labeling, not a broad NLE.
- Plugin SDK now: rejected because `ROADMAP.md` already parks it as a nice-to-have and the single-file architecture needs worker/model boundaries first.
- Cloud sync: rejected because it conflicts with the local-first differentiator and is already listed only as a nice-to-have.

## Sources
OSS and adjacent:
https://github.com/NickeManarin/ScreenToGif
https://www.screentogif.com/
https://github.com/lettier/gifcurry
https://lettier.github.io/gifcurry/
https://github.com/OfirKP/animeme
https://github.com/jeremyckahn/rekapi
https://github.com/ImageOptim/gifski
https://github.com/davisonio/awesome-gif
https://github.com/transitive-bullshit/awesome-ffmpeg

Commercial:
https://ezgif.com/add-text
https://ezgif.com/
https://www.kapwing.com/tools/add-text/gif
https://www.kapwing.com/tools/make/gif
https://www.veed.io/tools/add-text-to-video
https://www.veed.io/tools/add-subtitles
https://giphy.com/create/gifmaker
https://www.canva.com/create/gif-maker/

Standards and platform APIs:
https://www.w3.org/Graphics/GIF/spec-gif89a.txt
https://giflib.sourceforge.net/whatsinagif/animation_and_transparency.html
https://developers.google.com/speed/webp/docs/riff_container
https://developers.google.com/speed/webp/faq
https://wiki.mozilla.org/APNG_Specification
https://developer.mozilla.org/en-US/docs/Web/API/Web_Animations_API/Keyframe_Formats

Dependencies, security, and community:
https://www.qt.io/blog/qt-6.11.1-released
https://pillow.readthedocs.io/en/stable/releasenotes/index.html
https://pypi.org/project/opencv-python-headless/
https://pyinstaller.org/en/latest/CHANGES.html
https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
https://nvd.nist.gov/vuln/detail/cve-2026-42311
https://news.ycombinator.com/item?id=40426442

## Open Questions
- Needs live validation: how large a GIF should GifText officially support before warning or switching to streamed/temp-frame processing?
- Needs live validation: will the project ship source-first only, or should the Windows exe become the primary release artifact with signing and checksums?
