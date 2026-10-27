"""Versioned project model. All public time values are integer milliseconds."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

FORMAT = "tagmaker-project"
VERSION = "0.1"
LEVELS = ("BASIC", "STANDARD", "ADVANCED")


def new_id() -> str:
    return str(uuid4())


@dataclass
class Media:
    media_id: str
    path: str
    duration_ms: int | None = None
    size_bytes: int | None = None

    def validate(self) -> None:
        if not self.media_id or not self.path:
            raise ValueError("Media needs an ID and a path")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("Negative media duration")


@dataclass
class Event:
    event_id: str
    match_id: str
    type: str
    sport: str
    source_media_id: str
    source_time_ms: int
    global_video_time_ms: int
    period: str | None = None
    game_clock_ms: int | None = None
    clock_direction: str | None = None
    timestamp_quality: str = "player-reported-ms"
    team_id: str | None = None
    player_id: str | None = None
    related_event_ids: list[str] = field(default_factory=list)
    points: int | None = None
    note: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not all((self.event_id, self.match_id, self.type, self.sport, self.source_media_id)):
            raise ValueError("Event identity and source are required")
        if self.source_time_ms < 0 or self.global_video_time_ms < 0:
            raise ValueError("Negative video timestamp")
        if self.game_clock_ms is not None and self.game_clock_ms < 0:
            raise ValueError("Negative game clock")
        if self.clock_direction not in (None, "up", "down"):
            raise ValueError("Invalid clock direction")
        if self.points is not None and self.points < 0:
            raise ValueError("Negative points")
        if not isinstance(self.attributes, dict) or not isinstance(self.related_event_ids, list):
            raise ValueError("Invalid event payload")
        if not all(isinstance(item, str) for item in self.related_event_ids):
            raise ValueError("Invalid related event ID")
        try:
            json.dumps(self.attributes, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Event attributes must be finite JSON values") from exc
        if self.type in {"score_snapshot", "score_correction"}:
            scores = self.attributes.get("scores")
            if not isinstance(scores, dict) or not all(isinstance(k, str) and type(v) is int and v >= 0 for k, v in scores.items()):
                raise ValueError("Score snapshot needs nonnegative team scores")
        if self.type == "clock_sync":
            new_clock = self.attributes.get("new_game_clock_ms")
            if type(new_clock) is not int or new_clock < 0:
                raise ValueError("Clock sync needs new_game_clock_ms")
        if self.type == "substitution" and ("player_out_id" in self.attributes or "player_in_id" in self.attributes):
            outgoing = self.attributes.get("player_out_id")
            incoming = self.attributes.get("player_in_id")
            if not all(isinstance(item, str) and item for item in (outgoing, incoming)) or outgoing == incoming:
                raise ValueError("Substitution needs two different players")
            if self.player_id != outgoing:
                raise ValueError("Substitution player_id must be the outgoing player")


@dataclass
class Project:
    match_id: str
    name: str
    sport: str
    profile_id: str
    level: str = "BASIC"
    season: str = ""
    teams: list[dict[str, Any]] = field(default_factory=list)
    roster: list[dict[str, Any]] = field(default_factory=list)
    media: list[Media] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    period: str | None = None
    game_clock_ms: int | None = None
    clock_direction: str | None = None
    clock_running: bool = False
    clock_anchor_global_ms: int | None = None
    shortcuts: dict[str, str] = field(default_factory=dict)
    profile_data: dict[str, Any] = field(default_factory=dict)
    theme: str = "system"
    last_global_video_time_ms: int = 0

    def validate(self) -> None:
        if not self.match_id or not self.name or not self.sport:
            raise ValueError("Project identity is incomplete")
        if self.level not in LEVELS:
            raise ValueError("Unknown tagging level")
        if self.theme not in {"system", "dark", "light"}:
            raise ValueError("Unknown theme")
        if self.profile_data and (self.profile_data.get("id") != self.profile_id or self.profile_data.get("sport") != self.sport or not isinstance(self.profile_data.get("events"), list)):
            raise ValueError("Embedded sport profile does not match project")
        if self.game_clock_ms is not None and self.game_clock_ms < 0:
            raise ValueError("Negative project game clock")
        ids = [m.media_id for m in self.media]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate media IDs")
        for media in self.media:
            media.validate()
        seen: set[str] = set()
        team_ids = {t.get("id") for t in self.teams}
        player_ids = {p.get("id") for p in self.roster}
        if len(team_ids) != len(self.teams) or len(player_ids) != len(self.roster):
            raise ValueError("Duplicate team/player ID")
        if any(not isinstance(team.get("is_our_team", False), bool) for team in self.teams):
            raise ValueError("Invalid our squad marker")
        if sum(team.get("is_our_team", False) for team in self.teams) > 1:
            raise ValueError("More than one team is marked as our squad")
        for event in self.events:
            event.validate()
            if event.event_id in seen or event.match_id != self.match_id or event.sport != self.sport:
                raise ValueError("Duplicate or mismatched event")
            if event.source_media_id not in ids:
                raise ValueError("Event refers to missing media")
            if event.team_id is not None and event.team_id not in team_ids:
                raise ValueError("Event refers to missing team")
            if event.player_id is not None and event.player_id not in player_ids:
                raise ValueError("Event refers to missing player")
            if event.type == "substitution" and "player_in_id" in event.attributes:
                incoming = next((member for member in self.roster
                                 if member["id"] == event.attributes["player_in_id"]), None)
                outgoing = next((member for member in self.roster
                                 if member["id"] == event.player_id), None)
                if incoming is None or outgoing is None or any(member.get("team_id") != event.team_id
                                                                for member in (incoming, outgoing)):
                    raise ValueError("Substitution players must belong to the tagged team")
            if event.type in {"score_snapshot", "score_correction"} and any(team not in team_ids for team in event.attributes["scores"]):
                raise ValueError("Score refers to missing team")
            seen.add(event.event_id)
        for event in self.events:
            if any(related == event.event_id or related not in seen for related in event.related_event_ids):
                raise ValueError("Event relation refers to missing/self event")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"format": FORMAT, "version": VERSION, "project": asdict(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        if data.get("format") != FORMAT or data.get("version") != VERSION:
            raise ValueError("Unsupported TagMAKER format/version")
        raw = dict(data["project"])
        raw["media"] = [Media(**m) for m in raw.get("media", [])]
        raw["events"] = [Event(**e) for e in raw.get("events", [])]
        result = cls(**raw)
        result.validate()
        return result

    def resolve_media(self, media: Media, project_dir: Path) -> Path:
        path = Path(media.path)
        return path if path.is_absolute() else project_dir / path
