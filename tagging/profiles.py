"""JSON-formatted YAML profiles (JSON is a YAML 1.2 subset)."""
from __future__ import annotations
import json
from pathlib import Path

from tagging.model import LEVELS, Project

PROFILE_DIR = Path(__file__).resolve().parents[1] / "profiles"


def load_profile(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not data.get("id") or not data.get("sport") or not isinstance(data.get("events"), list):
        raise ValueError("Invalid sport profile")
    seen = set()
    keys = set()
    for event in data["events"]:
        if not event.get("type") or event.get("level") not in LEVELS or event["type"] in seen:
            raise ValueError("Invalid or duplicate profile event")
        if "points" in event and (not isinstance(event["points"], int) or event["points"] < 0):
            raise ValueError("Invalid points value")
        seen.add(event["type"])
        key = event.get("key")
        if key:
            if key in keys:
                raise ValueError("Duplicate profile shortcut")
            keys.add(key)
    return data


def available_profiles() -> list[dict]:
    return [load_profile(path) for path in sorted(PROFILE_DIR.glob("*.yaml"))]


def events_for_level(profile: dict, level: str) -> list[dict]:
    return [event for event in profile["events"] if LEVELS.index(event["level"]) <= LEVELS.index(level)]


def validate_event_type(project: Project, profile: dict, event_type: str, points: int | None) -> None:
    definitions = {e["type"]: e for e in events_for_level(profile, project.level)}
    if event_type not in definitions:
        raise ValueError(f"{event_type} is not enabled for {project.level}")
    definition = definitions[event_type]
    if definition.get("points") is not None and points != definition["points"]:
        raise ValueError("Points do not match profile definition")
