# GifText

![Version](https://img.shields.io/badge/version-v1.5.0-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-Python-lightgrey)

Add animated text to GIFs for meme creation. Track text labels on moving subjects with keyframe-based animation and smooth interpolation.

**The only actively maintained desktop app for animated GIF text editing.**

## Features

- **Video Import** - Load short video clips (MP4, WebM, AVI, MOV) with FPS, trim, and resize controls
- **Keyframe Animation** - Position, size, opacity, rotation, and color all animatable per-frame with smooth ease-in-out interpolation
- **OpenCV Motion Tracking** - Generate forward keyframes from the selected layer position with CSRT/KCF when available and optical-flow fallback
- **Bezier Path Animation** - Draw a four-point path and generate editable position keyframes over a chosen frame span
- **Motion Presets** - Generate editable Bounce, Wiggle, and Shake emphasis keyframes
- **Easing Curve Picker** - Choose per-keyframe cubic Bezier timing curves for interpolation
- **Staggered Text Reveal** - Reveal lines, words, or letters over time for animated captions
- **Subtitle Import** - Import SRT/VTT captions as timed editable text layers
- **Unicode Export Fallbacks** - Non-Latin captions use broader Windows font fallbacks during export rendering
- **Separate Stroke & Shadow Styling** - Tune stroke opacity plus shadow color/opacity independently
- **Responsive Long Jobs** - GIF loading, tracking, and export run in cancellable background workers
- **Structured Diagnostics** - Load, project, recent-file, tracking, and export failures write timestamped logs and appear in the in-app Diagnostics panel
- **On-Canvas Editing** - Click to select text, drag to reposition, drag corner handle to resize
- **Onion Skinning** - Ghost previous frame to track moving subjects
- **Multiple Text Layers** - Color-coded with individual timing controls
- **Layer Timeline** - Visual bars with keyframe diamonds and playhead
- **Range Tools** - Apply, copy, paste, delete, and visibility-limit keyframes across selected frame ranges
- **Fade In/Out** - Per-layer entry and exit animations
- **Meme Presets** - Classic Meme, Modern Clean, Subtitle, Bold Impact, Neon
- **Background Box** - Semi-transparent subtitle-style background
- **Undo/Redo** - Full 50-level undo history (Ctrl+Z / Ctrl+Y)
- **Project Save/Load** - Resume work later with `.giftext` project files
- **Versioned Project Schema** - Project loads validate schema, paths, frame ranges, colors, opacity, and keyframe fields before applying state
- **Multi-Format Export** - GIF, WebP (with alpha), PNG sequence, MP4, WebM
- **Trim Frames** - Cut start/end frames from the loaded source
- **Resize Source** - Downscale loaded frames for smaller output files
- **Zoom & Pan** - Ctrl+wheel to zoom, middle-click to pan
- **Drag & Drop** - Drop GIF files directly onto the canvas
- **Playback Speed** - 0.25x to 4x preview speed
- **Recent Files** - Quick access to previously opened GIFs
- **Multi-Line Text** - Full text area with line break support

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
python GifText.py
```

Dependencies:
- Python 3.10+
- PyQt6
- Pillow
- OpenCV
- NumPy
- imageio + imageio-ffmpeg (for video import)

## Workflow Example: Labeling People in a GIF

1. **Load** your GIF or video (or drag & drop it)
2. **Add text layers** - one per person/object
3. **Type names** in the text panel
4. **Drag** each name above its subject on frame 1
5. **Mousewheel** on canvas to step forward ~10 frames
6. **Drag** names to follow movement (keyframes auto-created)
7. Use **Track Forward** to generate motion keyframes when the subject is easy to follow
8. Use **Draw Path** when a label should follow a deliberate arc or swoop
9. Import `.srt` or `.vtt` captions when you want timed subtitle layers
10. Use **Bounce**, **Wiggle**, or **Shake** to add emphasis over the selected span
11. Repeat until the end - interpolation fills the gaps smoothly
12. **Export** as GIF, WebP, or PNG sequence

## Controls

| Action | Input |
|--------|-------|
| Step frames | Mousewheel on canvas |
| Zoom | Ctrl + Mousewheel |
| Pan | Middle-click drag |
| Select text | Click text on canvas |
| Move text | Drag text on canvas |
| Resize text | Drag bottom-right corner handle |
| Undo / Redo | Ctrl+Z / Ctrl+Y |
| Save project | Ctrl+S |

## Accessibility

All interactive controls expose accessible names and descriptions for screen readers. The canvas and timeline accept keyboard focus. High-contrast text on the dark theme passes readability checks.

## Tech Stack

- Python / PyQt6 for the GUI
- Pillow for GIF I/O and export rendering
- OpenCV and NumPy for forward motion tracking
- Modular architecture: models, animation, rendering, project I/O, diagnostics, workers, and UI

## Build Windows EXE

```bash
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\pyinstaller --clean GifText.spec
```

The executable is written to `dist\GifText.exe`.

### Release Build

The release script cleans build artifacts, runs PyInstaller, generates a SHA-256 checksum, and runs a smoke test:

```bash
python build_release.py
```

Options:
- `--skip-smoke` — skip the launch smoke test
- `--sign CERT.pfx` — code-sign the exe with a certificate

Outputs: `dist/GifText.exe` and `dist/GifText.exe.sha256`.

## Troubleshooting

Failures are shown in the status bar, written to the right-side Diagnostics panel, and appended to timestamped logs under `%USERPROFILE%\.giftext\logs\`. Use the **Export Diagnostics Bundle** button to save a text file with app version, dependency versions, OS details, project state, and recent log entries for bug reports. Project files are validated before loading so invalid `.giftext` files do not replace the current document.

## Command-Line Rendering

Render a `.giftext` project file without opening the GUI:

```bash
python GifText.py --render project.giftext -o output.gif
python GifText.py --render project.giftext -o video.mp4 -f mp4
```

Options:
- `--output` / `-o` — output file path (default: `<project>_rendered.gif`)
- `--format` / `-f` — output format: gif, webp, png, mp4, webm

## License

MIT
