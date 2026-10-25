"""A sequence of clips, with no multi-camera synchronization semantics."""
from dataclasses import dataclass
from tagging.model import Media


@dataclass(frozen=True)
class Position:
    media_id: str
    source_time_ms: int
    global_video_time_ms: int
    clip_index: int


class Timeline:
    def __init__(self, media: list[Media]):
        self.media = media

    def offset(self, index: int) -> int:
        durations = [m.duration_ms for m in self.media[:index]]
        if any(d is None for d in durations):
            raise ValueError("Earlier clip duration is unknown")
        return sum(durations)  # type: ignore[arg-type]

    def from_source(self, index: int, source_time_ms: int) -> Position:
        media = self.media[index]
        if source_time_ms < 0:
            raise ValueError("Negative source time")
        return Position(media.media_id, source_time_ms, self.offset(index) + source_time_ms, index)

    def from_global(self, global_time_ms: int) -> Position:
        if global_time_ms < 0 or not self.media:
            raise ValueError("Invalid global time")
        total = self.duration_ms
        if total is not None:
            global_time_ms = min(global_time_ms, total)
        start = 0
        for i, media in enumerate(self.media):
            if media.duration_ms is None:
                raise ValueError("Clip duration is unknown")
            end = start + media.duration_ms
            if global_time_ms < end or i == len(self.media) - 1:
                return Position(media.media_id, min(max(0, global_time_ms - start), media.duration_ms), global_time_ms, i)
            start = end
        raise AssertionError("Unreachable")

    @property
    def duration_ms(self) -> int | None:
        return sum(m.duration_ms for m in self.media) if all(m.duration_ms is not None for m in self.media) else None  # type: ignore[arg-type]
