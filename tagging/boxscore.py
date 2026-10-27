"""Observed basketball player counts for the in-app box score."""
from __future__ import annotations

from tagging.model import Project


STAT_FIELDS = ("points", "free_throws", "twos", "threes", "rebounds",
               "rebounds_off", "rebounds_def", "assists", "fouls",
               "turnovers", "subs_in", "subs_out")

EVENT_FIELD = {
    "score_1": "free_throws", "score_2": "twos", "score_3": "threes",
    "rebound": "rebounds", "rebound_off": "rebounds_off",
    "rebound_def": "rebounds_def", "assist": "assists", "foul": "fouls",
    "turnover": "turnovers",
}


def basketball_box_score(project: Project, team_id: str) -> tuple[list[dict], dict]:
    """Return observed counts; unknown statistics and playing minutes stay absent."""
    members = [member for member in project.roster if member.get("team_id") == team_id]
    tagged_ids = {event.player_id for event in project.events if event.team_id == team_id}
    tagged_ids.update(event.attributes.get("player_in_id") for event in project.events
                      if event.team_id == team_id and event.type == "substitution")
    rows = {}
    for member in members:
        if not member.get("called_up", True) and member["id"] not in tagged_ids:
            continue
        rows[member["id"]] = {"id": member["id"], "number": member.get("number"),
                              "name": member["name"], "starter": member.get("starter", False),
                              **{field: 0 for field in STAT_FIELDS}}
    summary = {"team_only_points": 0, "legacy_substitutions": 0,
               "complete_substitutions": 0}
    for event in project.events:
        if event.team_id != team_id:
            continue
        if event.type == "substitution":
            outgoing = event.attributes.get("player_out_id")
            incoming = event.attributes.get("player_in_id")
            if outgoing and incoming:
                summary["complete_substitutions"] += 1
                if outgoing in rows:
                    rows[outgoing]["subs_out"] += 1
                if incoming in rows:
                    rows[incoming]["subs_in"] += 1
            else:
                summary["legacy_substitutions"] += 1
            continue
        field = EVENT_FIELD.get(event.type)
        if field is None:
            continue
        if event.player_id not in rows:
            if event.points:
                summary["team_only_points"] += event.points
            continue
        row = rows[event.player_id]
        row[field] += 1
        if event.points:
            row["points"] += event.points
            continue
        if event.type in {"score_1", "score_2", "score_3"}:
            row["points"] += int(event.type[-1])
    ordered = sorted(rows.values(), key=lambda row: (not row["starter"], row["number"] is None,
                                                   row["number"] or 0, row["name"]))
    return ordered, summary
