import traceback
from datetime import datetime
from pathlib import Path


class DiagnosticsRecorder:
    def __init__(self, log_dir=None):
        base_dir = Path(log_dir) if log_dir else Path.home() / ".giftext" / "logs"
        self.log_dir = base_dir
        self.log_path = base_dir / f"errors-{datetime.now().strftime('%Y%m%d')}.log"

    def record(self, level, action, message, path=None, exc=None):
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        parts = [timestamp, level.upper(), action, message]
        if path:
            parts.append(f"path={path}")
        line = " | ".join(str(part) for part in parts if part)
        if exc is not None:
            line = f"{line}\n{traceback.format_exception_only(type(exc), exc)[-1].strip()}"
            trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            line = f"{line}\n{trace.rstrip()}"

        self.log_dir.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return line


def build_diagnostics_bundle(version, gif_path="", total_frames=0, layer_count=0,
                              log_dir=None, max_log_lines=50):
    import platform
    lines = [f"GifText v{version}", ""]
    lines.append("--- Environment ---")
    lines.append(f"OS: {platform.system()} {platform.release()} ({platform.version()})")
    lines.append(f"Python: {platform.python_version()}")
    lines.append(f"Architecture: {platform.machine()}")
    deps = {
        "PyQt6": "PyQt6.QtCore",
        "Pillow": "PIL",
        "OpenCV": "cv2",
        "NumPy": "numpy",
        "imageio": "imageio",
        "imageio-ffmpeg": "imageio_ffmpeg",
    }
    lines.append("")
    lines.append("--- Dependencies ---")
    for label, mod_name in deps.items():
        try:
            mod = __import__(mod_name)
            ver = getattr(mod, "__version__", getattr(mod, "PYQT_VERSION_STR", "?"))
            lines.append(f"{label}: {ver}")
        except ImportError:
            lines.append(f"{label}: not installed")
    lines.append("")
    lines.append("--- Project State ---")
    lines.append(f"Source: {gif_path or '(none)'}")
    lines.append(f"Frames: {total_frames}")
    lines.append(f"Layers: {layer_count}")
    if log_dir:
        log_path = Path(log_dir)
        if log_path.exists():
            log_files = sorted(log_path.glob("errors-*.log"), reverse=True)
            if log_files:
                lines.append("")
                lines.append(f"--- Recent Log ({log_files[0].name}) ---")
                try:
                    recent = log_files[0].read_text(encoding="utf-8").splitlines()
                    for entry in recent[-max_log_lines:]:
                        lines.append(entry)
                except Exception:
                    lines.append("(could not read log file)")
            else:
                lines.append("\n--- Logs ---\nNo error logs found.")
        else:
            lines.append("\n--- Logs ---\nLog directory does not exist.")
    return "\n".join(lines)
