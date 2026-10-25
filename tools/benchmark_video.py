"""Sample real clip startup, exact seeks, short playback, and process RAM.

Usage: python tools/benchmark_video.py path/to/clip.mp4 [path/to/clip.MTS]
The clips are read in place; no media bytes or frames are written.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playback.mpv_backend import MpvBackend  # noqa: E402
from tagging.model import Media  # noqa: E402


class ProcessMemory(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("page_fault_count", ctypes.c_ulong),
                *[(name, ctypes.c_size_t) for name in (
                    "peak_working_set", "working_set", "quota_peak_paged_pool",
                    "quota_paged_pool", "quota_peak_nonpaged_pool", "quota_nonpaged_pool",
                    "pagefile_usage", "peak_pagefile_usage", "private_usage")]]


def memory_mib() -> float:
    values = ProcessMemory()
    values.cb = ctypes.sizeof(values)
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = ctypes.c_void_p
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = (ctypes.c_void_p, ctypes.POINTER(ProcessMemory), ctypes.c_ulong)
    get_memory.restype = ctypes.c_bool
    if not get_memory(get_process(), ctypes.byref(values), values.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return round(values.working_set / (1024 * 1024), 1)


def wait_position(app: QApplication, backend: MpvBackend, target: int | None,
                  timeout: float = 30.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        app.processEvents()
        position, _ = backend.poll()
        if position and backend.player.video_params and (
                target is None or abs(position.source_time_ms - target) <= 500):
            return position
        time.sleep(0.03)
    raise TimeoutError(f"No decoded position near {target} within {timeout}s")


def benchmark(path: Path, app: QApplication, widget: QWidget) -> dict:
    media = Media("sample", str(path), size_bytes=path.stat().st_size)
    backend = MpvBackend(int(widget.winId()), [media], path.parent)
    record = {"path": str(path), "bytes": media.size_bytes, "ram_initial_mib": memory_mib()}
    try:
        started = time.perf_counter()
        backend.load(0, play=False)
        wait_position(app, backend, None)
        record["startup_to_position_ms"] = round((time.perf_counter() - started) * 1000)
        record["duration_ms"] = media.duration_ms
        record["ram_loaded_mib"] = memory_mib()
        if media.duration_ms is None:
            raise ValueError("libmpv did not report a clip duration")
        seeks = []
        for fraction in (0.1, 0.5, 0.9):
            target = round(media.duration_ms * fraction)
            started = time.perf_counter()
            backend.seek_global(target)
            actual = wait_position(app, backend, target)
            seeks.append({"target_ms": target, "actual_ms": actual.source_time_ms,
                          "elapsed_ms": round((time.perf_counter() - started) * 1000),
                          "ram_mib": memory_mib()})
        record["seeks"] = seeks
        backend.play_pause()
        started = time.perf_counter()
        time.sleep(0.1)
        while time.perf_counter() - started < 8:
            app.processEvents()
            backend.poll()
            time.sleep(0.03)
        backend.play_pause()
        position, _ = backend.poll()
        record["eight_second_playback_advanced_ms"] = (
            position.source_time_ms - seeks[-1]["actual_ms"] if position else None)
        record["ram_after_playback_mib"] = memory_mib()
        return record
    finally:
        backend.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips", nargs="+", type=Path)
    paths = parser.parse_args().clips
    app = QApplication([])
    widget = QWidget()
    widget.setAttribute(Qt.WA_NativeWindow)
    widget.resize(640, 360)
    widget.show()
    app.processEvents()
    try:
        for path in paths:
            print(json.dumps(benchmark(path.resolve(), app, widget), indent=2), flush=True)
    finally:
        widget.close()
        app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
