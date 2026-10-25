"""Portable JSON and aggregate CSV. Media bytes are never embedded."""
from __future__ import annotations
import csv
import copy
import json
import os
from pathlib import Path

from tagging.model import Project


def media_reference(source: str | Path, base_dir: str | Path) -> str:
    """Prefer a portable relative path; retain cross-drive paths for relinking."""
    try:
        return os.path.relpath(source, base_dir)
    except ValueError:
        return str(Path(source).resolve())


def export_json(project: Project, path: str | Path, project_dir: str | Path | None = None) -> None:
    target = Path(path)
    data = copy.deepcopy(project.to_dict())
    if project_dir is not None:
        for media in data["project"]["media"]:
            source = Path(media["path"])
            if not source.is_absolute(): source = Path(project_dir) / source
            media["path"] = media_reference(source, target.parent)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)


def import_json(path: str | Path) -> Project:
    with open(path, encoding="utf-8") as handle:
        return Project.from_dict(json.load(handle))


def export_csv(project: Project, path: str | Path) -> None:
    totals: dict[tuple[str, str, str], dict[str, int]] = {}
    for event in project.events:
        if event.type in {"score_snapshot", "score_correction"}:
            continue  # A snapshot is not an observed scoring event.
        key = (event.team_id or "", event.player_id or "", event.type)
        cell = totals.setdefault(key, {"count": 0, "points": 0})
        cell["count"] += 1
        cell["points"] += event.points or 0
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["format_version", "match_id", "sport", "team_id", "player_id", "event_type", "count", "observed_points"])
        for (team, player, kind), data in sorted(totals.items()):
            writer.writerow(["0.1", project.match_id, project.sport, team, player, kind, data["count"], data["points"]])
