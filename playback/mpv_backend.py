"""Small libmpv adapter. mpv decodes video; Python only reads timestamps."""
from __future__ import annotations
import os
import time
from pathlib import Path

from playback.timeline import Position, Timeline
from tagging.model import Media


_dll_directory_handle = None


def configure_libmpv(path: str | Path) -> None:
    """Use a DLL supplied by the user without copying it into TagMAKER."""
    global _dll_directory_handle
    dll = Path(path).resolve()
    if dll.name.casefold() != "libmpv-2.dll" or not dll.is_file():
        raise ValueError("Choose an existing libmpv-2.dll file")
    directory = str(dll.parent)
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if not any(entry.casefold() == directory.casefold() for entry in entries):
        os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        if _dll_directory_handle is not None:
            _dll_directory_handle.close()
        _dll_directory_handle = os.add_dll_directory(directory)


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.3f}"


class MpvBackend:
    def __init__(self, widget_id: int, media: list[Media], project_dir: Path):
        try:
            import mpv
        except (ImportError, OSError) as exc:
            raise RuntimeError("libmpv or python-mpv is unavailable; see README setup") from exc
        self.player = mpv.MPV(wid=str(widget_id & 0xffffffff), osc=False, input_default_bindings=False,
                              ytdl=False, hwdec="auto-safe", keep_open="yes", pause=True)
        self.media = media
        self.project_dir = project_dir
        self.timeline = Timeline(media)
        self.index = -1
        self.pending_seek_ms: int | None = None
        self.pending_play = False
        self.seek_wait_target_ms: int | None = None
        self.seek_requested_at = 0.0
        self._last_eof = False

    def close(self) -> None:
        self.player.terminate()

    def load(self, index: int, source_time_ms: int = 0, play: bool = False) -> None:
        media = self.media[index]
        path = Path(media.path)
        path = path if path.is_absolute() else self.project_dir / path
        if not path.is_file():
            raise FileNotFoundError(f"Missing clip: {path}")
        self.index = index
        self.pending_seek_ms = source_time_ms
        self.seek_wait_target_ms = None
        self.pending_play = play
        self._last_eof = False
        self.player.pause = True
        self.player.command("loadfile", str(path), "replace")

    def poll(self) -> tuple[Position | None, bool]:
        if self.index < 0:
            return None, False
        media = self.media[self.index]
        actual = self.player.path
        expected = Path(media.path)
        expected = expected if expected.is_absolute() else self.project_dir / expected
        if not actual or Path(actual).resolve() != expected.resolve():
            return None, False
        duration = self.player.duration
        duration_changed = False
        if duration is not None and duration > 0:
            measured = int(round(float(duration) * 1000))
            if media.duration_ms != measured:
                media.duration_ms = measured
                duration_changed = True
        if self.pending_seek_ms is not None:
            # libmpv may report the path/duration before a large file is ready
            # to accept seek commands. Opening at zero needs no seek at all.
            if self.pending_seek_ms and not self.player.video_params:
                return None, duration_changed
            if self.pending_seek_ms:
                self._seek_source(self.pending_seek_ms)
            self.pending_seek_ms = None
            self.player.pause = not self.pending_play
            return None, duration_changed
        source_ms = max(0, int(round(float(self.player.time_pos or 0) * 1000)))
        if self.seek_wait_target_ms is not None:
            # mpv seeks asynchronously. Never expose the pre-seek position to tagging.
            if abs(source_ms - self.seek_wait_target_ms) > 500 and time.monotonic() - self.seek_requested_at < 4:
                return None, duration_changed
            self.seek_wait_target_ms = None
        try:
            position = self.timeline.from_source(self.index, source_ms)
        except ValueError:
            return None, duration_changed
        eof = bool(self.player.eof_reached)
        if eof and not self._last_eof and self.index + 1 < len(self.media):
            self.load(self.index + 1, 0, play=True)
            return None, duration_changed
        self._last_eof = eof
        return position, duration_changed

    def seek_global(self, global_ms: int) -> None:
        pos = self.timeline.from_global(global_ms)
        if pos.clip_index != self.index:
            self.load(pos.clip_index, pos.source_time_ms, play=not self.player.pause)
        else:
            self._seek_source(pos.source_time_ms)

    def _seek_source(self, source_time_ms: int) -> None:
        self.seek_wait_target_ms = source_time_ms
        self.seek_requested_at = time.monotonic()
        self.player.command("seek", _seconds(source_time_ms), "absolute+exact")

    def play_pause(self) -> None:
        if self.index < 0:
            self.load(0, play=True)
        else:
            self.player.pause = not self.player.pause

    def step_frame(self) -> None:
        if self.index >= 0:
            self.player.command("frame-step")

    def skip(self, delta_ms: int) -> None:
        if self.index < 0:
            return
        position, _ = self.poll()
        if position:
            duration = self.timeline.duration_ms
            target = max(0, position.global_video_time_ms + delta_ms)
            if duration is not None:
                target = min(target, duration)
            self.seek_global(target)

    def set_speed(self, speed: float) -> None:
        self.player.speed = speed

    def set_volume(self, volume: int) -> None:
        self.player.volume = volume


def probe_duration(path: Path, timeout_seconds: float = 12) -> int | None:
    """Read container duration through a separate native mpv instance."""
    import mpv
    probe = mpv.MPV(vo="null", ao="null", pause=True, osc=False)
    try:
        probe.command("loadfile", str(path), "replace")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if probe.duration:
                return int(round(float(probe.duration) * 1000))
            if probe.eof_reached:
                return None
            time.sleep(0.05)
        return None
    finally:
        probe.terminate()
