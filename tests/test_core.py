from pathlib import Path
import csv
import os
import time
import json
import gc

import pytest
from jsonschema import Draft202012Validator

from playback.timeline import Timeline
from storage.database import load_project, save_project
from storage.interchange import export_csv, export_json, import_json
from storage.webmaker import (WebMakerGame, export_webmaker_stats, import_group,
                              load_webmaker_games, load_webmaker_roster)
from tagging.clock import clock_at, set_running, sync_clock
from tagging.model import Event, Media, Project
from tagging.profiles import load_profile, events_for_level

QT_APP = None


@pytest.fixture(scope="module", autouse=True)
def close_qt_after_tests():
    yield
    global QT_APP
    if QT_APP is not None:
        QT_APP.closeAllWindows()
        QT_APP.processEvents()
        QT_APP.quit()
        QT_APP = None
        gc.collect()


def qt_app():
    global QT_APP
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    if QT_APP is None:
        QT_APP = QApplication.instance() or QApplication([])
    return QT_APP


def sample() -> Project:
    project = Project("match", "Test match", "basketball", "basketball", teams=[{"id": "home", "name": "Home"}])
    project.media = [Media("one", "one.mp4", 10_001), Media("two", "two.mp4", 20_000)]
    return project


def test_timeline_clip_boundary_and_units():
    timeline = Timeline(sample().media)
    assert timeline.from_source(1, 37).global_video_time_ms == 10_038
    assert timeline.from_global(10_001).media_id == "two"
    assert timeline.from_global(10_001).source_time_ms == 0
    assert timeline.duration_ms == 30_001
    with pytest.raises(ValueError): timeline.from_global(-1)


def test_clock_preserves_manual_sync_and_stop():
    project = sample(); project.clock_direction = "down"
    sync_clock(project, 600_000, 20_000)
    set_running(project, True, 20_000)
    assert clock_at(project, 23_500) == 596_500
    set_running(project, False, 23_500)
    assert clock_at(project, 80_000) == 596_500
    sync_clock(project, 590_000, 80_000)
    assert clock_at(project, 80_000) == 590_000


def test_autosave_reopen_and_portable_export(tmp_path: Path):
    project = sample()
    project.events.append(Event("event", "match", "score_2", "basketball", "two", 100,
                                10_101, period="Q1", game_clock_ms=None, team_id="home", points=2))
    db = tmp_path / "project" / "match.sqlite3"
    save_project(db, project)
    reopened = load_project(db)
    assert reopened.events[0].global_video_time_ms == 10_101
    assert reopened.events[0].game_clock_ms is None
    exported = tmp_path / "export" / "match.json"
    exported.parent.mkdir()
    export_json(reopened, exported, db.parent)
    imported = import_json(exported)
    assert imported.media[0].path == str(Path("..") / "project" / "one.mp4")
    assert imported.events[0].points == 2
    csv_path = tmp_path / "stats.csv"
    export_csv(imported, csv_path)
    assert "observed_points" in csv_path.read_text(encoding="utf-8-sig")
    assert ",2\n" in csv_path.read_text(encoding="utf-8-sig")


def test_validation_rejects_missing_media_and_unknown_version():
    project = sample()
    project.events.append(Event("event", "match", "goal", "basketball", "missing", 0, 0))
    with pytest.raises(ValueError, match="missing media"):
        project.to_dict()
    project.events.clear()
    payload = project.to_dict(); payload["version"] = "9.0"
    with pytest.raises(ValueError, match="Unsupported"):
        Project.from_dict(payload)


def test_profiles_are_independent():
    basketball = load_profile(Path(__file__).parents[1] / "profiles" / "basketball.yaml")
    football = load_profile(Path(__file__).parents[1] / "profiles" / "football.yaml")
    assert {e["type"] for e in events_for_level(basketball, "BASIC")} != {e["type"] for e in events_for_level(football, "BASIC")}
    assert "goal" in {e["type"] for e in events_for_level(football, "BASIC")}


def test_custom_profile_travels_with_project(tmp_path: Path):
    profile = {"id": "custom", "sport": "custom", "events": [{"type": "point", "level": "BASIC"}]}
    project = Project("custom-match", "Custom", "custom", "custom", profile_data=profile)
    target = tmp_path / "custom.sqlite3"
    save_project(target, project)
    assert load_project(target).profile_data == profile


def test_profile_rejects_conflicting_shortcuts(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text(json.dumps({"id": "bad", "sport": "bad", "events": [
        {"type": "one", "level": "BASIC", "key": "A"},
        {"type": "two", "level": "BASIC", "key": "A"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate profile shortcut"):
        load_profile(path)


def test_webmaker_roster_import_keeps_ids_and_jersey_numbers(tmp_path: Path):
    data = tmp_path / "webmaker" / "site" / "data"
    (data / "players").mkdir(parents=True)
    (data / "teams.yaml").write_text("nerone:\n  name: Nerone Basket Anzio\n", encoding="utf-8")
    (data / "players" / "ada.yaml").write_text("id: ada\nname: Ada Rossi\n", encoding="utf-8")
    (data / "players" / "bea.yaml").write_text("id: bea\nname: Bea Verdi\n", encoding="utf-8")
    (data / "rosters.csv").write_text(
        "season,competition,team_id,player_id,number,role,active\n"
        "2026-27,platinum,nerone,ada,0,,true\n"
        "2026-27,platinum,nerone,bea,12,,false\n", encoding="utf-8")
    candidates = load_webmaker_roster(tmp_path / "webmaker")
    assert [(item.name, item.number, item.active) for item in candidates] == [
        ("Ada Rossi", 0, True), ("Bea Verdi", 12, False)]
    project = Project("match-web", "Web", "basketball", "basketball", level="ADVANCED",
                      teams=[{"id": "home", "name": "Nerone Basket Anzio"}])
    assert import_group(project, candidates, "home", {"ada"}) == (2, 0)
    first_id = project.roster[0]["id"]
    assert project.roster[0]["number"] == 0
    assert project.roster[1]["called_up"] is False
    assert import_group(project, candidates, "home", {"bea"}) == (0, 2)
    assert project.roster[0]["id"] == first_id
    assert project.roster[0]["called_up"] is False
    assert project.roster[1]["called_up"] is True
    project.validate()


def test_webmaker_games_and_observed_stats_export(tmp_path: Path):
    root = tmp_path / "webmaker"
    data = root / "site" / "data"
    (data / "players").mkdir(parents=True)
    (data / "games" / "2026-27").mkdir(parents=True)
    (data / "rosters.csv").write_text("season,competition,team_id,player_id,number\n", encoding="utf-8")
    (data / "games" / "2026-27" / "platinum.csv").write_text(
        "id,date,home_team,away_team\ngame-1,2026-10-25,nerone,away\n", encoding="utf-8")
    games = load_webmaker_games(root)
    assert [(game.game_id, game.season, game.competition) for game in games] == [
        ("game-1", "2026-27", "platinum")]
    project = Project("match", "Test", "basketball", "basketball",
                      teams=[{"id": "home", "name": "Home"}])
    project.media = [Media("clip", "clip.MTS", 20_000)]
    project.roster = [{"id": "tag-player", "team_id": "home", "name": "Ada",
                       "webmaker_player_id": "ada", "webmaker_team_id": "nerone"}]
    project.events = [
        Event("score", "match", "score_3", "basketball", "clip", 100, 100,
              team_id="home", player_id="tag-player", points=3),
        Event("assist", "match", "assist", "basketball", "clip", 200, 200,
              team_id="home", player_id="tag-player"),
        Event("team-foul", "match", "foul", "basketball", "clip", 300, 300,
              team_id="home"),
        Event("generic-rebound", "match", "rebound", "basketball", "clip", 400, 400,
              team_id="home", player_id="tag-player"),
    ]
    target = tmp_path / "stats.csv"
    assert export_webmaker_stats(project, games[0], target) == (1, 1, 1)
    with target.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert {key: rows[0][key] for key in ("game_id", "player_id", "points",
                                           "three_pointers_made", "assists", "minutes", "fouls")} == {
        "game_id": "game-1", "player_id": "ada", "points": "3",
        "three_pointers_made": "1", "assists": "1", "minutes": "", "fouls": ""}
    project.roster[0].pop("webmaker_player_id")
    with pytest.raises(ValueError, match="no WebMAKER player ID"):
        export_webmaker_stats(project, games[0], target)


def test_webmaker_export_action_uses_real_game_id(tmp_path: Path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    from app.main import MainWindow

    app = qt_app()
    data = tmp_path / "webmaker" / "site" / "data"
    (data / "players").mkdir(parents=True)
    (data / "games" / "2026-27").mkdir(parents=True)
    (data / "rosters.csv").write_text("season,competition,team_id,player_id,number\n", encoding="utf-8")
    (data / "games" / "2026-27" / "platinum.csv").write_text(
        "id,date,home_team,away_team\nreal-game,2026-10-25,nerone,away\n", encoding="utf-8")
    project = Project("match", "Match", "basketball", "basketball",
                      teams=[{"id": "home", "name": "Home"}])
    profile = load_profile(Path(__file__).parents[1] / "profiles" / "basketball.yaml")
    window = MainWindow(project, tmp_path / "match.sqlite3", profile)
    window.project.media = [Media("clip", "clip.MTS", 1000)]
    window.project.roster = [{"id": "tag-player", "team_id": "home", "name": "Ada",
                              "webmaker_player_id": "ada", "webmaker_team_id": "nerone"}]
    window.project.events = [Event("score", "match", "score_2", "basketball", "clip", 100, 100,
                                   team_id="home", player_id="tag-player", points=2)]
    target = tmp_path / "studio-import.csv"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(data.parent.parent))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args, **kwargs: ("2026-10-25 · nerone / away · real-game", True))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), "CSV (*.csv)"))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_error", lambda message: (_ for _ in ()).throw(AssertionError(message)))
    window.export_webmaker()
    with target.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert (row["game_id"], row["player_id"], row["points"]) == ("real-game", "ada", "2")
    window.close(); window.deleteLater(); app.processEvents()


def test_mts_file_filter():
    from app.main import VIDEO_FILE_FILTER

    assert "*.mts" in VIDEO_FILE_FILTER and "*.MTS" in VIDEO_FILE_FILTER


def test_shared_schema_fixture_when_checked_out_together():
    """Run the cross-repository contract check in a PlayMAKER workspace."""

    root = Path(__file__).parents[2]
    if not (root / "playmaker-schema" / "tagmaker-project-0.1.schema.json").exists():
        pytest.skip("playmaker-schema is not checked out alongside tagmaker")
    fixture = json.loads((root / "playmaker-schema" / "fixtures" /
                          "tagmaker-project-0.1.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "playmaker-schema" /
                         "tagmaker-project-0.1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(fixture)
    project = Project.from_dict(fixture)
    Draft202012Validator(schema).validate(project.to_dict())
    assert project.to_dict()["version"] == schema["properties"]["version"]["const"]
    assert project.events[1].global_video_time_ms == 10_100


def test_webmaker_convocati_dialog_and_player_selector(tmp_path: Path):
    from PySide6.QtCore import Qt
    from app.main import ConvocatiDialog, MainWindow, WebMakerRosterDialog
    from storage.webmaker import RosterCandidate

    app = qt_app()
    project = Project("match-web", "Web", "basketball", "basketball", level="ADVANCED",
                      teams=[{"id": "home", "name": "Nerone Basket Anzio"}])
    rows = [
        RosterCandidate("2026-27", "platinum", "nerone", "Nerone Basket Anzio", "ada", "Ada Rossi", 0, "", True),
        RosterCandidate("2026-27", "platinum", "nerone", "Nerone Basket Anzio", "bea", "Bea Verdi", 12, "", False),
    ]
    dialog = WebMakerRosterDialog(rows, project)
    assert dialog.table.rowCount() == 2
    assert dialog.called_up_ids() == {"ada"}
    target_team = dialog.target_pick.currentData()
    import_group(project, dialog.source_rows(), target_team, dialog.called_up_ids())
    dialog.close(); dialog.deleteLater()
    convocati = ConvocatiDialog(project.roster)
    assert convocati.called_up_ids() == {project.roster[0]["id"]}
    convocati.table.item(1, 0).setCheckState(Qt.Checked)
    selected = convocati.called_up_ids()
    for member in project.roster:
        member["called_up"] = member["id"] in selected
    convocati.close(); convocati.deleteLater()
    profile = load_profile(Path(__file__).parents[1] / "profiles" / "basketball.yaml")
    window = MainWindow(project, tmp_path / "convocati.sqlite3", profile)
    window.show(); app.processEvents()
    assert window.tag_scroll.verticalScrollBar().maximum() == 0
    first = window.tag_layout.itemAt(0).widget()
    next_row = window.tag_layout.itemAt(2).widget()
    assert next_row.y() - (first.y() + first.height()) <= 6
    assert window.log.height() <= 160
    assert not window.windowIcon().isNull()
    window.team.setCurrentIndex(1)
    assert [window.player_pick.itemText(i) for i in range(window.player_pick.count())] == [
        "—", "#0 Ada Rossi", "#12 Bea Verdi"]
    window.close(); window.deleteLater(); app.processEvents()


def test_webmaker_import_action_reuses_match_player(tmp_path: Path, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from app.main import MainWindow, WebMakerRosterDialog

    app = qt_app()
    source = tmp_path / "webmaker" / "site" / "data"
    (source / "players").mkdir(parents=True)
    (source / "teams.yaml").write_text("nerone:\n  name: Nerone Basket Anzio\n", encoding="utf-8")
    (source / "players" / "ada.yaml").write_text("id: ada\nname: Ada Rossi\n", encoding="utf-8")
    (source / "rosters.csv").write_text(
        "season,competition,team_id,player_id,number,role,active\n"
        "2026-27,platinum,nerone,ada,0,,true\n", encoding="utf-8")
    monkeypatch.setattr("app.main.QFileDialog.getExistingDirectory", lambda *_args: str(tmp_path / "webmaker"))
    monkeypatch.setattr(WebMakerRosterDialog, "exec", lambda _self: QDialog.Accepted)
    project = Project("web-match", "Web", "basketball", "basketball",
                      teams=[{"id": "home", "name": "Nerone Basket Anzio"}])
    profile = load_profile(Path(__file__).parents[1] / "profiles" / "basketball.yaml")
    window = MainWindow(project, tmp_path / "match.sqlite3", profile)
    window.import_webmaker()
    assert len(window.project.roster) == 1
    assert window.project.roster[0]["number"] == 0
    player_id = window.project.roster[0]["id"]
    assert window.team.currentData() == "home"
    assert window.player_pick.itemText(1) == "#0 Ada Rossi"
    window.import_webmaker()
    assert len(window.project.roster) == 1
    assert window.project.roster[0]["id"] == player_id
    window.close()
    assert load_project(window.path).roster[0]["id"] == player_id
    window.deleteLater(); app.processEvents()


def test_gui_tag_undo_redo_and_save(tmp_path: Path):
    from app.main import ClipOrderDialog, MainWindow
    from playback.timeline import Position

    app = qt_app()
    ordering = ClipOrderDialog(["first.mp4", "second.mp4", "third.mp4"])
    ordering.list.setCurrentRow(2)
    ordering.move(-1)
    assert ordering.ordered_files() == ["first.mp4", "third.mp4", "second.mp4"]
    ordering.close()
    ordering.deleteLater()
    project = sample()
    path = tmp_path / "gui.sqlite3"
    profile = load_profile(Path(__file__).parents[1] / "profiles" / "basketball.yaml")
    window = MainWindow(Project("m", "GUI", "basketball", "basketball", teams=project.teams), path, profile)
    window.project.media = project.media
    window.theme_pick.setCurrentText("Dark")
    assert window.project.theme == "dark"
    window.position = Position("two", 100, 10_101, 1)
    window.team.setCurrentIndex(1)
    window.tag("score_2")
    assert len(window.project.events) == 1
    window.undo(); assert not window.project.events
    window.redo(); assert window.project.events[0].points == 2
    window.close()
    assert load_project(path).events[0].global_video_time_ms == 10_101
    window.deleteLater()
    app.processEvents()
    assert app is not None


def test_missing_clip_is_reported(tmp_path: Path):
    from playback.mpv_backend import MpvBackend

    backend = MpvBackend.__new__(MpvBackend)
    backend.media = [Media("missing", "absent.mp4")]
    backend.project_dir = tmp_path
    with pytest.raises(FileNotFoundError, match="Missing clip"):
        backend.load(0)


def test_large_autosave_yields_to_ui(tmp_path: Path):
    from app.main import MainWindow

    app = qt_app()
    project = sample()
    project.events = [Event(str(i), "match", "turnover", "basketball", "one", i, i)
                      for i in range(10_000)]
    profile = load_profile(Path(__file__).parents[1] / "profiles" / "basketball.yaml")
    # Construct without media to avoid needing libmpv, then attach the model clips.
    initial_media = project.media
    project.media = []
    window = MainWindow(project, tmp_path / "large.sqlite3", profile)
    window.project.media = initial_media
    window._changed()
    window._queue_save()
    assert window.capture_index == 0  # first 200-event slice is scheduled, not blocking this call
    # Cloud-synced folders can make the final disk flush much slower than the
    # event-loop capture; the scheduling assertion above is the UI check.
    deadline = time.monotonic() + 30
    while window.save_label.text() != "Saved" and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.save_label.text() == "Saved"
    assert len(load_project(window.path).events) == 10_000
    window.close()
    window.deleteLater()
    app.processEvents()
