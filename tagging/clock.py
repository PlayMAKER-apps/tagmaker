"""Manual game clock; video time never substitutes for game time."""
from tagging.model import Project


def clock_at(project: Project, global_video_ms: int) -> int | None:
    base = project.game_clock_ms
    anchor = project.clock_anchor_global_ms
    if base is None or not project.clock_running or anchor is None:
        return base
    elapsed = max(0, global_video_ms - anchor)
    return max(0, base - elapsed) if project.clock_direction == "down" else base + elapsed


def sync_clock(project: Project, value_ms: int, global_video_ms: int) -> None:
    if value_ms < 0:
        raise ValueError("Negative clock")
    project.game_clock_ms = value_ms
    project.clock_anchor_global_ms = global_video_ms


def set_running(project: Project, running: bool, global_video_ms: int) -> None:
    current = clock_at(project, global_video_ms)
    project.game_clock_ms = current
    project.clock_anchor_global_ms = global_video_ms
    project.clock_running = running
