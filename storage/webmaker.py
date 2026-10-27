"""Read WebMAKER's source roster files without changing that project."""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from tagging.model import Project, new_id


@dataclass(frozen=True)
class RosterCandidate:
    season: str
    competition: str
    source_team_id: str
    team_name: str
    source_player_id: str
    name: str
    number: int | None
    role: str
    active: bool

    @property
    def group(self) -> tuple[str, str, str]:
        return self.season, self.competition, self.source_team_id


@dataclass(frozen=True)
class WebMakerGame:
    game_id: str
    date: str
    season: str
    competition: str
    home_team: str
    away_team: str

    @property
    def label(self) -> str:
        return f"{self.date} · {self.home_team} / {self.away_team} · {self.game_id}"


def _data_dir(source: str | Path) -> Path:
    path = Path(source)
    if path.is_file() and path.name.lower() == "rosters.csv":
        path = path.parent
    for candidate in (path / "site" / "data", path):
        if (candidate / "rosters.csv").is_file() and (candidate / "players").is_dir():
            return candidate
    raise ValueError("Select a WebMAKER project containing site/data/rosters.csv and site/data/players")


def _yaml_mapping(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Invalid YAML mapping: {path}")
    return value


def load_webmaker_roster(source: str | Path) -> list[RosterCandidate]:
    data_dir = _data_dir(source)
    teams = _yaml_mapping(data_dir / "teams.yaml")
    players: dict[str, str] = {}
    player_files = [*(data_dir / "players").glob("*.yaml"), *(data_dir / "players").glob("*.yml")]
    for path in sorted(player_files):
        if path.name.startswith("_"):
            continue
        player = _yaml_mapping(path)
        player_id, name = str(player.get("id", "")).strip(), str(player.get("name", "")).strip()
        if not player_id or not name or player_id in players:
            raise ValueError(f"Missing or duplicate player identity: {path}")
        players[player_id] = name
    result: list[RosterCandidate] = []
    seen: set[tuple[str, str, str, str]] = set()
    with (data_dir / "rosters.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"season", "competition", "team_id", "player_id", "number"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("WebMAKER roster CSV is missing required columns")
        for line, row in enumerate(reader, start=2):
            season = (row.get("season") or "").strip()
            competition = (row.get("competition") or "").strip()
            team_id = (row.get("team_id") or "nerone").strip()
            player_id = (row.get("player_id") or "").strip()
            if not all((season, competition, team_id, player_id)):
                raise ValueError(f"Incomplete roster row {line}")
            key = season, competition, team_id, player_id
            if key in seen:
                raise ValueError(f"Duplicate roster membership on row {line}")
            seen.add(key)
            if team_id not in teams or not isinstance(teams[team_id], dict):
                raise ValueError(f"Unknown team {team_id} on row {line}")
            if player_id not in players:
                raise ValueError(f"Unknown player {player_id} on row {line}")
            raw_number = (row.get("number") or "").strip()
            if raw_number:
                if not raw_number.isdecimal() or int(raw_number) > 999:
                    raise ValueError(f"Invalid jersey number on row {line}")
                number = int(raw_number)
            else:
                number = None
            active_text = (row.get("active") or "true").strip().lower()
            if active_text not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError(f"Invalid active value on row {line}")
            result.append(RosterCandidate(
                season=season, competition=competition, source_team_id=team_id,
                team_name=str(teams[team_id].get("name") or team_id).strip(),
                source_player_id=player_id, name=players[player_id], number=number,
                role=(row.get("role") or "").strip(),
                active=active_text in {"true", "1", "yes"},
            ))
    if not result:
        raise ValueError("WebMAKER roster has no players")
    return result


def load_webmaker_games(source: str | Path) -> list[WebMakerGame]:
    """Read published game IDs from a WebMAKER source tree."""
    games_dir = _data_dir(source) / "games"
    result: list[WebMakerGame] = []
    seen: set[str] = set()
    for path in sorted(games_dir.glob("*/*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not {"id", "home_team", "away_team"}.issubset(reader.fieldnames):
                raise ValueError(f"WebMAKER games CSV has missing columns: {path}")
            for row in reader:
                game_id = (row.get("id") or "").strip()
                if not game_id or game_id in seen:
                    raise ValueError(f"Missing or duplicate WebMAKER game ID: {game_id}")
                seen.add(game_id)
                result.append(WebMakerGame(game_id, (row.get("date") or "").strip(),
                                           path.parent.name, path.stem,
                                           (row.get("home_team") or "").strip(),
                                           (row.get("away_team") or "").strip()))
    if not result:
        raise ValueError("No WebMAKER games found under site/data/games/<season>/*.csv")
    return result


WEBMAKER_STATS_COLUMNS = (
    "game_id", "player_id", "minutes", "points", "three_pointers_made",
    "two_pointers_made", "free_throws_made", "fouls", "rebounds_off",
    "rebounds_def", "assists", "turnovers",
)
_STAT_FOR_EVENT = {
    "score_1": "free_throws_made", "score_2": "two_pointers_made",
    "score_3": "three_pointers_made", "foul": "fouls",
    "rebound_off": "rebounds_off", "rebound_def": "rebounds_def",
    "assist": "assists", "turnover": "turnovers",
}


def export_webmaker_stats(project: Project, game: WebMakerGame, path: str | Path) -> tuple[int, int, int]:
    """Write only observed, player-attributed basketball statistics.

    Blank cells mean unmeasured, including minutes. Existing WebMAKER records
    are never modified: Studio imports this CSV as new records only.
    """
    if project.sport != "basketball":
        raise ValueError("WebMAKER player-stat export currently supports basketball only")
    if not game.game_id:
        raise ValueError("Choose a WebMAKER game ID")
    roster = {member["id"]: member for member in project.roster}
    observed: dict[str, dict[str, int]] = {}
    skipped = 0
    unclassified_rebounds = 0
    for event in project.events:
        if event.type == "rebound":
            unclassified_rebounds += 1
            continue
        stat = _STAT_FOR_EVENT.get(event.type)
        if stat is None:
            continue
        if not event.player_id:
            skipped += 1
            continue
        member = roster.get(event.player_id)
        if member is None or not member.get("webmaker_player_id"):
            raise ValueError(f"Tagged player {event.player_id} has no WebMAKER player ID")
        if member.get("team_id") != event.team_id:
            raise ValueError(f"Tagged player {event.player_id} belongs to another team")
        if member.get("webmaker_team_id") not in {game.home_team, game.away_team}:
            raise ValueError(f"Tagged player {event.player_id} is not on either WebMAKER game team")
        source_id = str(member["webmaker_player_id"])
        cell = observed.setdefault(source_id, {})
        cell[stat] = cell.get(stat, 0) + 1
        if event.type in {"score_1", "score_2", "score_3"}:
            cell["points"] = cell.get("points", 0) + (event.points if event.points is not None else int(event.type[-1]))
    if not observed:
        raise ValueError("No player-attributed WebMAKER statistics to export")
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WEBMAKER_STATS_COLUMNS)
        writer.writeheader()
        for source_id, counts in sorted(observed.items()):
            writer.writerow({"game_id": game.game_id, "player_id": source_id,
                             **counts})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return len(observed), skipped, unclassified_rebounds


def import_group(project: Project, rows: list[RosterCandidate], target_team_id: str,
                 called_up_ids: set[str]) -> tuple[int, int]:
    """Merge one source group; existing TagMAKER player IDs remain stable."""
    if not rows or len({row.group for row in rows}) != 1:
        raise ValueError("Select one WebMAKER season, competition and team")
    if target_team_id not in {team["id"] for team in project.teams}:
        raise ValueError("Target team is missing")
    added = updated = 0
    for row in rows:
        member = next((item for item in project.roster
                       if item.get("team_id") == target_team_id
                       and item.get("webmaker_player_id") == row.source_player_id), None)
        if member is None:
            member = next((item for item in project.roster
                           if item.get("team_id") == target_team_id
                           and item.get("webmaker_player_id") is None
                           and str(item.get("name", "")).casefold() == row.name.casefold()), None)
        if member is None:
            member = {"id": new_id(), "team_id": target_team_id}
            project.roster.append(member)
            added += 1
        else:
            updated += 1
        member.update({
            "name": row.name, "number": row.number, "role": row.role,
            "active": row.active, "called_up": row.source_player_id in called_up_ids,
            "webmaker_player_id": row.source_player_id,
            "webmaker_team_id": row.source_team_id,
            "webmaker_season": row.season,
            "webmaker_competition": row.competition,
        })
        if not member["called_up"]:
            member["starter"] = False
    return added, updated
