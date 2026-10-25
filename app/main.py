"""TagMAKER desktop application."""
from __future__ import annotations
import copy
import ctypes
import json
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QIntValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSlider,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from playback.mpv_backend import MpvBackend, probe_duration
from playback.timeline import Timeline
from storage.database import load_project, save_project
from storage.interchange import export_csv, export_json, import_json, media_reference
from storage.webmaker import (RosterCandidate, export_webmaker_stats, import_group,
                              load_webmaker_games, load_webmaker_roster)
from tagging.clock import clock_at, set_running, sync_clock
from tagging.model import Event, Media, Project, new_id
from tagging.profiles import available_profiles, events_for_level, load_profile, validate_event_type

ICON_PATH = Path(__file__).resolve().parent / "assets" / "tagmaker.ico"
VIDEO_FILE_FILTER = (
    "Video files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.mts *.m2ts *.MTS *.M2TS);;All files (*)"
)


def fmt(ms: int | None) -> str:
    if ms is None:
        return "--:--.---"
    seconds, millis = divmod(max(0, ms), 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02}:{seconds:02}.{millis:03}"


def parse_clock(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("Use MM:SS or MM:SS.mmm")
    minute = int(parts[0]); second = float(parts[1])
    if minute < 0 or not 0 <= second < 60:
        raise ValueError("Clock is out of range")
    return minute * 60000 + round(second * 1000)


class StartDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TagMAKER — choose project")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        self.profile = QComboBox()
        self.profiles = available_profiles()
        for item in self.profiles:
            self.profile.addItem(item["label"], item)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Match name")
        self.season = QLineEdit()
        self.season.setPlaceholderText("Season / year")
        self.level = QComboBox(); self.level.addItems(["BASIC", "STANDARD", "ADVANCED"])
        self.team_a = QLineEdit(); self.team_a.setPlaceholderText("Home team")
        self.team_b = QLineEdit(); self.team_b.setPlaceholderText("Away team")
        form = QFormLayout()
        for label, widget in [("Sport profile", self.profile), ("Match", self.name),
                              ("Season", self.season), ("Detail", self.level),
                              ("Team 1", self.team_a), ("Team 2", self.team_b)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        for label, action in [("New project", self.make_new), ("Open project", self.open_existing),
                              ("Import JSON", self.import_existing), ("Load custom profile", self.custom_profile)]:
            button = QPushButton(label); button.clicked.connect(action); buttons.addWidget(button)
        layout.addLayout(buttons)
        self.project: Project | None = None
        self.path: Path | None = None
        self.profile_data: dict | None = None

    def custom_profile(self):
        file, _ = QFileDialog.getOpenFileName(self, "Choose profile", "", "Profile (*.yaml *.json)")
        if file:
            try:
                data = load_profile(file)
                self.profiles.append(data)
                self.profile.addItem(data.get("label", data["id"]), data)
                self.profile.setCurrentIndex(self.profile.count() - 1)
            except Exception as exc:
                QMessageBox.warning(self, "Profile error", str(exc))

    def make_new(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Match name", "Enter a match name."); return
        file, _ = QFileDialog.getSaveFileName(self, "New project", self.name.text().strip() + ".tagmaker.sqlite3", "TagMAKER (*.sqlite3)")
        if not file: return
        if Path(file).exists():
            QMessageBox.warning(self, "Project exists", "Choose a new project file."); return
        profile = self.profile.currentData()
        teams = [{"id": new_id(), "name": name.strip()} for name in (self.team_a.text(), self.team_b.text()) if name.strip()]
        self.project = Project(new_id(), self.name.text().strip(), profile["sport"], profile["id"],
                               self.level.currentText(), self.season.text().strip(), teams=teams,
                               clock_direction=profile.get("clock_direction"), period=profile.get("periods", [None])[0],
                               profile_data=profile)
        self.path = Path(file)
        self.profile_data = profile
        save_project(self.path, self.project)
        self.accept()

    def open_existing(self):
        file, _ = QFileDialog.getOpenFileName(self, "Open project", "", "TagMAKER (*.sqlite3)")
        if not file: return
        try:
            self.project = load_project(file)
            self.path = Path(file)
            self.profile_data = self.project.profile_data or next((p for p in self.profiles if p["id"] == self.project.profile_id), None)
            if self.profile_data is None:
                raise ValueError("Custom profile: load its file first, then open the project")
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, "Open failed", str(exc))

    def import_existing(self):
        file, _ = QFileDialog.getOpenFileName(self, "Import JSON", "", "JSON (*.json)")
        if not file: return
        try:
            project = import_json(file)
            profile = project.profile_data or next((p for p in self.profiles if p["id"] == project.profile_id), None)
            if profile is None: raise ValueError("Load the matching custom profile first")
            db, _ = QFileDialog.getSaveFileName(self, "Save imported project", Path(file).stem + ".tagmaker.sqlite3", "TagMAKER (*.sqlite3)")
            if not db: return
            if Path(db).exists(): raise ValueError("Choose a new database file")
            # Rebase media paths from the JSON's location to the new project location.
            for media in project.media:
                source = Path(media.path)
                if not source.is_absolute(): source = Path(file).parent / source
                media.path = media_reference(source, Path(db).parent)
            save_project(db, project)
            self.project, self.path, self.profile_data = project, Path(db), profile
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", str(exc))


class ClipOrderDialog(QDialog):
    def __init__(self, files: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Consecutive clip order")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arrange clips from the start to the end of the match."))
        self.list = QListWidget()
        for file in files:
            self.list.addItem(file)
        layout.addWidget(self.list)
        controls = QHBoxLayout()
        for label, offset in (("Move up", -1), ("Move down", 1)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, delta=offset: self.move(delta))
            controls.addWidget(button)
        layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def move(self, delta: int):
        row = self.list.currentRow()
        next_row = row + delta
        if 0 <= row < self.list.count() and 0 <= next_row < self.list.count():
            item = self.list.takeItem(row)
            self.list.insertItem(next_row, item)
            self.list.setCurrentRow(next_row)

    def ordered_files(self) -> list[str]:
        return [self.list.item(index).text() for index in range(self.list.count())]


class WebMakerRosterDialog(QDialog):
    def __init__(self, rows: list[RosterCandidate], project: Project, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.project = project
        self.setWindowTitle("Import WebMAKER roster · choose convocati")
        self.resize(680, 600)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.source_pick = QComboBox()
        groups = sorted({row.group for row in rows})
        for group in groups:
            first = next(row for row in rows if row.group == group)
            self.source_pick.addItem(f"{first.season} · {first.competition} · {first.team_name}", group)
        matching_season = next((i for i, group in enumerate(groups) if group[0] == project.season), 0)
        self.source_pick.setCurrentIndex(matching_season)
        form.addRow("WebMAKER roster", self.source_pick)
        self.target_pick = QComboBox()
        form.addRow("TagMAKER team", self.target_pick)
        layout.addLayout(form)
        layout.addWidget(QLabel("Check the players called up for this match. All roster members are imported."))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Convocato", "Number", "Player"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for label, checked in (("Select all", True), ("Select none", False)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, state=checked: self._set_all(state))
            actions.addWidget(button)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.source_pick.currentIndexChanged.connect(self._source_changed)
        self.target_pick.currentIndexChanged.connect(self._populate_players)
        self._source_changed()

    def source_rows(self) -> list[RosterCandidate]:
        group = self.source_pick.currentData()
        return sorted((row for row in self.rows if row.group == group),
                      key=lambda row: (row.number is None, row.number if row.number is not None else 0, row.name))

    def _source_changed(self):
        rows = self.source_rows()
        if not rows:
            return
        source = rows[0]
        self.target_pick.blockSignals(True)
        self.target_pick.clear()
        for team in self.project.teams:
            self.target_pick.addItem(team["name"], team["id"])
        self.target_pick.addItem(f"Create {source.team_name}", None)
        match = next((i for i, team in enumerate(self.project.teams)
                      if team.get("webmaker_team_id") == source.source_team_id
                      or team["name"].casefold() == source.team_name.casefold()), -1)
        if match < 0:
            match = next((i for i, team in enumerate(self.project.teams)
                          if team["name"].casefold() in source.team_name.casefold()
                          or source.team_name.casefold() in team["name"].casefold()),
                         self.target_pick.count() - 1)
        self.target_pick.setCurrentIndex(match)
        self.target_pick.blockSignals(False)
        self._populate_players()

    def _populate_players(self):
        self.table.setRowCount(0)
        target_team_id = self.target_pick.currentData()
        for candidate in self.source_rows():
            row = self.table.rowCount()
            self.table.insertRow(row)
            existing = next((item for item in self.project.roster
                             if item.get("team_id") == target_team_id
                             and item.get("webmaker_player_id") == candidate.source_player_id), None)
            checked = existing.get("called_up", True) if existing else candidate.active
            choice = QTableWidgetItem()
            choice.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            choice.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            choice.setData(Qt.UserRole, candidate.source_player_id)
            self.table.setItem(row, 0, choice)
            self.table.setItem(row, 1, QTableWidgetItem("" if candidate.number is None else str(candidate.number)))
            self.table.setItem(row, 2, QTableWidgetItem(candidate.name + (" (inactive in WebMAKER)" if not candidate.active else "")))

    def _set_all(self, checked: bool):
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def called_up_ids(self) -> set[str]:
        return {self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount())
                if self.table.item(row, 0).checkState() == Qt.Checked}


class ConvocatiDialog(QDialog):
    def __init__(self, players: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Convocati for this match")
        self.resize(480, 560)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Convocato", "Number", "Player"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        for member in sorted(players, key=lambda item: (item.get("number") is None, item.get("number") or 0, item["name"])):
            row = self.table.rowCount()
            self.table.insertRow(row)
            choice = QTableWidgetItem()
            choice.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            choice.setCheckState(Qt.Checked if member.get("called_up", True) else Qt.Unchecked)
            choice.setData(Qt.UserRole, member["id"])
            self.table.setItem(row, 0, choice)
            self.table.setItem(row, 1, QTableWidgetItem("" if member.get("number") is None else str(member["number"])))
            self.table.setItem(row, 2, QTableWidgetItem(member["name"]))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def called_up_ids(self) -> set[str]:
        return {self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount())
                if self.table.item(row, 0).checkState() == Qt.Checked}


class MainWindow(QMainWindow):
    def __init__(self, project: Project, path: Path, profile: dict):
        super().__init__()
        self.project, self.path, self.profile = project, path, profile
        self.setWindowTitle(f"TagMAKER — {project.name}")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1280, 800)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tagmaker-save")
        self.probe_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tagmaker-probe")
        self.save_future: Future | None = None
        self.probe_future: Future | None = None
        self.probe_attempted: set[str] = set()
        self.dirty = False
        self.revision = 0
        self.capture_base: Project | None = None
        self.capture_events: list[Event] = []
        self.capture_index = 0
        self.capture_revision = 0
        self.undo_stack: list[list[Event]] = []
        self.redo_stack: list[list[Event]] = []
        self.position = None
        self.last_resume_saved_ms = project.last_global_video_time_ms
        self.shortcuts: list[QShortcut] = []
        self.event_shortcuts: list[QShortcut] = []
        self.pending_tag: Event | None = None
        self.player: MpvBackend | None = None
        self._build_ui()
        self._refresh_all()
        self._bind_shortcuts()
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(100)
        self.autosave = QTimer(self); self.autosave.setSingleShot(True)
        self.autosave.timeout.connect(self._queue_save)
        if self.project.media:
            self._ensure_player()
            if self.player:
                try:
                    try:
                        previous = Timeline(self.project.media).from_global(self.project.last_global_video_time_ms)
                        self.player.load(previous.clip_index, previous.source_time_ms, play=False)
                    except ValueError:
                        self.player.load(0, 0, play=False)
                except Exception as exc: self._error(str(exc))
            self._probe_missing()

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        toolbar = QHBoxLayout()
        self._button(toolbar, "Add clips", self.add_clips)
        self._button(toolbar, "Relink missing", self.relink)
        self._button(toolbar, "Add team", self.add_team)
        self._button(toolbar, "Export JSON", self.export_project)
        self._button(toolbar, "Export CSV", self.export_stats)
        self._button(toolbar, "Export WebMAKER", self.export_webmaker)
        self._button(toolbar, "Shortcuts", self.edit_shortcuts)
        self.theme_pick = QComboBox()
        self.theme_pick.addItems(["System", "Dark", "Light"])
        self.theme_pick.setCurrentText(self.project.theme.capitalize())
        self.theme_pick.currentTextChanged.connect(self._theme_changed)
        toolbar.addWidget(self.theme_pick)
        self.save_label = QLabel("Saved"); toolbar.addStretch(); toolbar.addWidget(self.save_label)
        outer.addLayout(toolbar)
        splitter = QSplitter(Qt.Horizontal); outer.addWidget(splitter, 1)
        left = QWidget(); lv = QVBoxLayout(left)
        self.video = QWidget(); self.video.setAttribute(Qt.WA_NativeWindow); self.video.setStyleSheet("background:#101217")
        self.video.setMinimumSize(480, 270); lv.addWidget(self.video, 1)
        self.source_label = QLabel("No clip"); lv.addWidget(self.source_label)
        self.seek = QSlider(Qt.Horizontal); self.seek.setRange(0, 0); self.seek.sliderReleased.connect(self._seek_release); lv.addWidget(self.seek)
        controls = QHBoxLayout()
        self._button(controls, "−5s", lambda: self._skip(-5000))
        self._button(controls, "Play / Pause", self._toggle_play)
        self._button(controls, "+5s", lambda: self._skip(5000))
        self._button(controls, "Frame", self._frame)
        self.speed = QComboBox()
        for rate in ("0.25", "0.5", "0.75", "1", "1.25", "1.5", "2"):
            self.speed.addItem(rate)
        self.speed.setCurrentText("1"); self.speed.currentTextChanged.connect(self._speed)
        controls.addWidget(QLabel("Speed")); controls.addWidget(self.speed)
        self.volume = QSlider(Qt.Horizontal); self.volume.setRange(0, 100); self.volume.setValue(80)
        self.volume.setMaximumWidth(100); self.volume.valueChanged.connect(self._volume)
        controls.addWidget(QLabel("Volume")); controls.addWidget(self.volume)
        lv.addLayout(controls)
        self.clock_label = QLabel("Game clock: --:--.---")
        lv.addWidget(self.clock_label)
        clock_row = QHBoxLayout()
        self.period = QComboBox(); self.period.addItems(self.profile.get("periods", [])); self.period.currentTextChanged.connect(self._period_changed)
        clock_row.addWidget(self.period)
        self._button(clock_row, "Clock start/stop", self._clock_toggle)
        self._button(clock_row, "Sync clock", self._clock_sync)
        lv.addLayout(clock_row)
        splitter.addWidget(left)
        right = QWidget(); rv = QVBoxLayout(right)
        self.score = QLabel("Observed points: —"); rv.addWidget(self.score)
        roster_actions = QHBoxLayout()
        self._button(roster_actions, "Our squad", self.set_our_team)
        self._button(roster_actions, "Import WebMAKER", self.import_webmaker)
        self._button(roster_actions, "Convocati", self.edit_convocati)
        self._button(roster_actions, "Add player", self.add_player)
        rv.addLayout(roster_actions)
        self.tag_prompt = QLabel()
        self.tag_prompt.setVisible(False)
        rv.addWidget(self.tag_prompt)
        self.tags = QWidget(); self.tag_layout = QGridLayout(self.tags)
        self.tag_layout.setContentsMargins(4, 4, 4, 4)
        self.tag_layout.setSpacing(4)
        self.tag_layout.setAlignment(Qt.AlignTop)
        self.tag_scroll = QScrollArea()
        self.tag_scroll.setWidgetResizable(True)
        self.tag_scroll.setWidget(self.tags)
        self.tag_scroll.setMinimumHeight(350)
        rv.addWidget(self.tag_scroll, 4)
        self._button(rv, "Score snapshot / correction", self.score_correction)
        self._button(rv, "Undo (Ctrl+Z)", self.undo)
        self._button(rv, "Redo (Ctrl+Y)", self.redo)
        rv.addWidget(QLabel("Events — double click to edit"))
        self.log = QTableWidget(0, 5)
        self.log.setMinimumHeight(105)
        self.log.setMaximumHeight(160)
        self.log.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.log.setHorizontalHeaderLabels(["Video", "Game", "Type", "Team", "Note"])
        self.log.cellDoubleClicked.connect(self.edit_event)
        rv.addWidget(self.log, 1)
        splitter.addWidget(right); splitter.setSizes([800, 480])
        self._apply_theme()

    def _theme_changed(self, value: str):
        self.project.theme = value.lower()
        self._apply_theme()
        self._changed()

    def _apply_theme(self):
        base = "QWidget { font-size: 13px; } QPushButton { padding: 5px 9px; }"
        if self.project.theme == "dark":
            base += " QWidget { background:#20242b; color:#e9edf2; } QPushButton, QComboBox, QLineEdit, QTableWidget, QScrollArea { background:#303844; color:#e9edf2; border:1px solid #596473; }"
        elif self.project.theme == "light":
            base += " QWidget { background:#f5f6f8; color:#1e2630; } QPushButton, QComboBox, QLineEdit, QTableWidget, QScrollArea { background:#ffffff; color:#1e2630; border:1px solid #aab4c0; }"
        self.setStyleSheet(base)

    def _button(self, layout, label, callback):
        button = QPushButton(label); button.clicked.connect(callback); layout.addWidget(button)
        return button

    def _ensure_player(self):
        if self.player: return
        try:
            self.player = MpvBackend(int(self.video.winId()), self.project.media, self.path.parent)
        except Exception as exc:
            self._error(str(exc))

    def _error(self, message):
        QMessageBox.warning(self, "TagMAKER", message)

    def _changed(self):
        self.revision += 1
        self.dirty = True
        self.save_label.setText("Unsaved…")
        self.autosave.start(350)

    def _queue_save(self):
        if self.capture_base is not None:
            return
        if self.save_future is not None:
            if not self.save_future.done():
                self.autosave.start(350)
                return
            try:
                self.save_future.result()
            except Exception as exc:
                self.save_future = None
                self.dirty = True
                self.save_label.setText("Save failed")
                self._error(str(exc))
                return
            self.save_future = None
        try:
            self.capture_base = copy.deepcopy(replace(self.project, events=[]))
            self.capture_events = list(self.project.events)
            self.capture_index = 0
            self.capture_revision = self.revision
        except Exception as exc:
            self._error(str(exc)); return
        self.save_label.setText("Preparing save…")
        QTimer.singleShot(0, self._capture_chunk)

    def _capture_chunk(self):
        if self.capture_base is None:
            return
        if self.capture_revision != self.revision:
            self.capture_base = None
            self.capture_events = []
            self.autosave.start(350)
            return
        stop = min(self.capture_index + 200, len(self.capture_events))
        self.capture_base.events.extend(copy.deepcopy(self.capture_events[self.capture_index:stop]))
        self.capture_index = stop
        if stop < len(self.capture_events):
            QTimer.singleShot(0, self._capture_chunk)
            return
        snapshot = self.capture_base
        self.capture_base = None
        self.capture_events = []
        self.save_future = self.executor.submit(save_project, self.path, snapshot)
        self.dirty = False
        self.save_label.setText("Saving…")

    def _tick(self):
        if self.save_future and self.save_future.done():
            try: self.save_future.result(); self.save_label.setText("Unsaved…" if self.dirty else "Saved")
            except Exception as exc:
                self.dirty = True
                self.save_label.setText("Save failed")
                self._error(str(exc))
            self.save_future = None
        if self.probe_future and self.probe_future.done():
            try:
                media_id, duration = self.probe_future.result()
                media = next(m for m in self.project.media if m.media_id == media_id)
                if duration and media.duration_ms != duration:
                    media.duration_ms = duration; self._changed()
            except Exception as exc: self.statusBar().showMessage(f"Clip probe failed: {exc}", 8000)
            self.probe_future = None; self._probe_missing()
        if not self.player: return
        try: position, changed = self.player.poll()
        except Exception as exc:
            self.statusBar().showMessage(f"Playback error: {exc}", 8000); return
        if changed: self._changed()
        if position:
            self.position = position
            if abs(position.global_video_time_ms - self.last_resume_saved_ms) >= 5000:
                self.project.last_global_video_time_ms = position.global_video_time_ms
                self.last_resume_saved_ms = position.global_video_time_ms
                self._changed()
            if not self.seek.isSliderDown():
                duration = Timeline(self.project.media).duration_ms
                self.seek.setMaximum(duration or 0); self.seek.setValue(position.global_video_time_ms)
            media = self.project.media[position.clip_index]
            self.source_label.setText(f"Clip {position.clip_index + 1}/{len(self.project.media)}: {Path(media.path).name}  {fmt(position.source_time_ms)}   |   Match video {fmt(position.global_video_time_ms)}")
            self.clock_label.setText(f"Game clock: {fmt(clock_at(self.project, position.global_video_time_ms))}  {'running' if self.project.clock_running else 'stopped'}")
        else:
            self.position = None

    def _probe_missing(self):
        if self.probe_future: return
        for media in self.project.media:
            if media.duration_ms is None and media.media_id not in self.probe_attempted:
                path = self.project.resolve_media(media, self.path.parent)
                if path.is_file():
                    self.probe_attempted.add(media.media_id)
                    self.probe_future = self.probe_executor.submit(lambda id=media.media_id, p=path: (id, probe_duration(p)))
                    return
        if self.project.media and Timeline(self.project.media).duration_ms is None:
            self.statusBar().showMessage("Some clip durations are unknown; relink or replace unreadable clips.", 10000)

    def add_clips(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Choose consecutive clips in order", "", VIDEO_FILE_FILTER)
        if not files: return
        if len(files) > 1:
            ordering = ClipOrderDialog(files, self)
            if ordering.exec() != QDialog.Accepted:
                return
            files = ordering.ordered_files()
        for file in files:
            media = Media(new_id(), media_reference(file, self.path.parent), size_bytes=Path(file).stat().st_size)
            self.project.media.append(media)
        self._changed(); self._refresh_all(); self._ensure_player()
        if self.player and self.player.index < 0:
            try: self.player.load(0)
            except Exception as exc: self._error(str(exc))
        self._probe_missing()

    def relink(self):
        for media in self.project.media:
            if self.project.resolve_media(media, self.path.parent).is_file(): continue
            file, _ = QFileDialog.getOpenFileName(self, f"Locate {Path(media.path).name}")
            if file:
                actual_size = Path(file).stat().st_size
                if media.size_bytes is not None and actual_size != media.size_bytes:
                    self._error("This file's size differs from the original clip. Choose the same recording to preserve event timestamps.")
                    continue
                media.path = media_reference(file, self.path.parent)
                media.size_bytes = actual_size
                self.probe_attempted.discard(media.media_id)
                self._changed()
        self._probe_missing()

    def add_player(self):
        team_id = self._our_team_id()
        if team_id is None:
            self._error("Add a team before adding players.")
            return
        name, ok = QInputDialog.getText(self, "Roster", "Player name")
        if not ok or not name.strip(): return
        number, ok = QInputDialog.getInt(self, "Roster", "Jersey number (-1 if unknown)", -1, -1, 999)
        if not ok: return
        self.project.roster.append({"id": new_id(), "name": name.strip(), "team_id": team_id,
                                    "called_up": True, "number": None if number == -1 else number})
        self._changed(); self._render_tags()

    def import_webmaker(self):
        folder = QFileDialog.getExistingDirectory(self, "Select WebMAKER project folder", str(Path.home()))
        if not folder:
            return
        try:
            rows = load_webmaker_roster(folder)
        except Exception as exc:
            self._error(f"WebMAKER import failed: {exc}")
            return
        dialog = WebMakerRosterDialog(rows, self.project, self)
        if dialog.exec() != QDialog.Accepted:
            return
        chosen = dialog.source_rows()
        source_team = chosen[0]
        target_team_id = dialog.target_pick.currentData()
        if target_team_id is None:
            target_team_id = new_id()
            self.project.teams.append({"id": target_team_id, "name": source_team.team_name,
                                       "webmaker_team_id": source_team.source_team_id})
        else:
            target = next(team for team in self.project.teams if team["id"] == target_team_id)
            linked = target.get("webmaker_team_id")
            if linked and linked != source_team.source_team_id:
                self._error("This TagMAKER team is already linked to another WebMAKER team. Choose a different team.")
                return
            target["webmaker_team_id"] = source_team.source_team_id
        try:
            added, updated = import_group(self.project, chosen, target_team_id, dialog.called_up_ids())
        except Exception as exc:
            self._error(f"WebMAKER import failed: {exc}")
            return
        if not self.project.season:
            self.project.season = source_team.season
        self._changed()
        self._refresh_all()
        self._mark_our_team(target_team_id)
        self.statusBar().showMessage(f"WebMAKER roster: {added} added, {updated} updated. Choose Convocati to adjust the match list.", 10000)

    def edit_convocati(self):
        team_id = self._our_team_id()
        if team_id is None:
            self._error("Add or select our squad before choosing convocati.")
            return
        members = [item for item in self.project.roster if item.get("team_id") == team_id]
        if not members:
            self._error("This team has no players yet. Import a WebMAKER roster or add players.")
            return
        dialog = ConvocatiDialog(members, self)
        if dialog.exec() != QDialog.Accepted:
            return
        selected = dialog.called_up_ids()
        for member in members:
            member["called_up"] = member["id"] in selected
        self._changed()
        self._render_tags()

    def add_team(self):
        name, ok = QInputDialog.getText(self, "Team", "Team name")
        if not ok or not name.strip(): return
        if any(team["name"].casefold() == name.strip().casefold() for team in self.project.teams):
            self._error("A team with this name already exists."); return
        self.project.teams.append({"id": new_id(), "name": name.strip()})
        self._changed()
        self._refresh_all()

    def _our_team_id(self):
        marked = next((team["id"] for team in self.project.teams if team.get("is_our_team")), None)
        if marked is not None:
            return marked
        roster_teams = {member.get("team_id") for member in self.project.roster}
        return next((team["id"] for team in self.project.teams if team["id"] in roster_teams),
                    self.project.teams[0]["id"] if self.project.teams else None)

    def _mark_our_team(self, team_id):
        for team in self.project.teams:
            team["is_our_team"] = team["id"] == team_id
        self._changed()
        self._render_tags()

    def set_our_team(self):
        if not self.project.teams:
            self._error("Add a team first.")
            return
        names = [team["name"] for team in self.project.teams]
        current = next((i for i, team in enumerate(self.project.teams)
                        if team["id"] == self._our_team_id()), 0)
        name, ok = QInputDialog.getItem(self, "Our squad", "Select the team whose players you tag",
                                        names, current, False)
        if ok:
            self._mark_our_team(self.project.teams[names.index(name)]["id"])

    def _refresh_all(self):
        self.period.blockSignals(True); self.period.setCurrentText(self.project.period or ""); self.period.blockSignals(False)
        self._render_tags()
        self._refresh_log()

    def _render_tags(self):
        while self.tag_layout.count():
            child = self.tag_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()
        self.tag_prompt.setVisible(self.pending_tag is not None)
        if self.pending_tag is not None:
            self._render_assignment()
            return
        for index, definition in enumerate(events_for_level(self.profile, self.project.level)):
            label = definition["label"] + (f" [{self.project.shortcuts.get(definition['type'], definition.get('key'))}]" if self.project.shortcuts.get(definition["type"], definition.get("key")) else "")
            button = QPushButton(label)
            button.setFixedHeight(34)
            button.clicked.connect(lambda _=False, kind=definition["type"]: self.tag(kind))
            self.tag_layout.addWidget(button, index // 2, index % 2)

    def _render_assignment(self):
        definition = next(e for e in self.profile["events"] if e["type"] == self.pending_tag.type)
        our_id = self._our_team_id()
        our_team = next((team for team in self.project.teams if team["id"] == our_id), None)
        self.tag_prompt.setText(f"{definition['label']} at {fmt(self.pending_tag.global_video_time_ms)} — choose who")
        members = [member for member in self.project.roster
                   if member.get("team_id") == our_id and member.get("called_up", True)]
        members.sort(key=lambda member: (member.get("number") is None, member.get("number") or 0, member["name"]))
        self.number_entry = QLineEdit()
        self.number_entry.setPlaceholderText("Jersey number + Enter")
        self.number_entry.setValidator(QIntValidator(0, 999, self.number_entry))
        self.number_entry.returnPressed.connect(self._choose_number)
        self.tag_layout.addWidget(self.number_entry, 0, 0, 1, 2)
        for index, member in enumerate(members):
            number = member.get("number")
            label = f"#{number} {member['name']}" if number is not None else member["name"]
            button = QPushButton(label)
            button.setFixedHeight(34)
            button.clicked.connect(lambda _=False, player=member: self._choose_actor(our_id, player["id"]))
            self.tag_layout.addWidget(button, 1 + index // 2, index % 2)
        row = 1 + (len(members) + 1) // 2
        if our_team and not members:
            button = QPushButton(f"{our_team['name']} (team only)")
            button.clicked.connect(lambda: self._choose_actor(our_id, None))
            self.tag_layout.addWidget(button, row, 0, 1, 2)
            row += 1
        for team in self.project.teams:
            if team["id"] == our_id:
                continue
            button = QPushButton(f"{team['name']} (opponent team)")
            button.setFixedHeight(34)
            button.clicked.connect(lambda _=False, team_id=team["id"]: self._choose_actor(team_id, None))
            self.tag_layout.addWidget(button, row, 0, 1, 2)
            row += 1
        cancel = QPushButton("Cancel (Esc)")
        cancel.clicked.connect(self._cancel_tag)
        self.tag_layout.addWidget(cancel, row, 0, 1, 2)
        self.number_entry.setEnabled(bool(members))
        if members:
            self.number_entry.setFocus()

    def _choose_number(self):
        if self.pending_tag is None:
            return
        number = int(self.number_entry.text()) if self.number_entry.text() else None
        matches = [member for member in self.project.roster
                   if member.get("team_id") == self._our_team_id() and member.get("called_up", True)
                   and member.get("number") == number and number is not None]
        if len(matches) == 1:
            self._choose_actor(self._our_team_id(), matches[0]["id"])
        else:
            self.tag_prompt.setText("Jersey number not found or ambiguous — choose a player button")

    def _choose_actor(self, team_id, player_id):
        if self.pending_tag is None:
            return
        event = self.pending_tag
        event.team_id, event.player_id = team_id, player_id
        self._cancel_tag()
        self._commit_event(event)

    def _cancel_tag(self):
        if self.pending_tag is None:
            return
        self.pending_tag = None
        for shortcut in self.event_shortcuts:
            shortcut.setEnabled(True)
        self._render_tags()

    def _remember(self):
        self.undo_stack.append(copy.deepcopy(self.project.events))
        self.undo_stack = self.undo_stack[-100:]
        self.redo_stack.clear()

    def _current_time(self):
        if self.player:
            try:
                self.position, changed = self.player.poll()
                if changed:
                    self._changed()
            except Exception as exc:
                self._error(str(exc)); return None
        if not self.position:
            self._error("Load and seek a video before tagging."); return None
        return self.position

    def _add_event(self, kind: str, points: int | None = None, attributes: dict | None = None):
        pos = self._current_time()
        if pos is None: return
        event = Event(new_id(), self.project.match_id, kind, self.project.sport,
                      pos.media_id, pos.source_time_ms, pos.global_video_time_ms,
                      period=self.project.period, game_clock_ms=clock_at(self.project, pos.global_video_time_ms),
                      clock_direction=self.project.clock_direction, points=points, attributes=attributes or {})
        self._commit_event(event)

    def _commit_event(self, event: Event):
        self._remember(); self.project.events.append(event)
        self.project.last_global_video_time_ms = event.global_video_time_ms
        self._changed(); self._refresh_log()

    def tag(self, kind: str):
        definition = next(e for e in self.profile["events"] if e["type"] == kind)
        points = definition.get("points")
        try: validate_event_type(self.project, self.profile, kind, points)
        except ValueError as exc: self._error(str(exc)); return
        if kind in {"score_snapshot", "score_correction"}:
            self.score_correction(kind)
            return
        if kind in {"period_start", "period_end", "game_start", "game_stop",
                    "clock_sync"}:
            self._add_event(kind, points)
            return
        pos = self._current_time()
        if pos is None: return
        if not self.project.teams:
            self._error("Add teams before tagging this event.")
            return
        self.pending_tag = Event(new_id(), self.project.match_id, kind, self.project.sport,
                                 pos.media_id, pos.source_time_ms, pos.global_video_time_ms,
                                 period=self.project.period,
                                 game_clock_ms=clock_at(self.project, pos.global_video_time_ms),
                                 clock_direction=self.project.clock_direction, points=points)
        for shortcut in self.event_shortcuts:
            shortcut.setEnabled(False)
        self._render_tags()

    def _refresh_log(self):
        self.log.setRowCount(0)
        for event in sorted(self.project.events, key=lambda e: e.global_video_time_ms):
            row = self.log.rowCount(); self.log.insertRow(row)
            team = next((t["name"] for t in self.project.teams if t["id"] == event.team_id), "")
            values = [fmt(event.global_video_time_ms), fmt(event.game_clock_ms), event.type, team, event.note]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value); item.setData(Qt.UserRole, event.event_id); self.log.setItem(row, col, item)
        observed = {team["id"]: 0 for team in self.project.teams}
        for event in sorted(self.project.events, key=lambda e: e.global_video_time_ms):
            if event.type in {"score_snapshot", "score_correction"}:
                observed.update(event.attributes.get("scores", {}))
            elif event.points is not None and event.team_id in observed:
                observed[event.team_id] += event.points
        self.score.setText("Recorded score: " + "  |  ".join(f"{t['name']} {observed[t['id']]}" for t in self.project.teams))

    def edit_event(self, row, _column):
        event_id = self.log.item(row, 0).data(Qt.UserRole)
        event = next(e for e in self.project.events if e.event_id == event_id)
        dialog = QDialog(self); dialog.setWindowTitle("Edit event")
        form = QFormLayout(dialog)
        note = QLineEdit(event.note); form.addRow("Note", note)
        team = QComboBox(); team.addItem("—", None)
        for t in self.project.teams: team.addItem(t["name"], t["id"])
        team.setCurrentIndex(max(0, team.findData(event.team_id))); form.addRow("Team", team)
        player = QComboBox(); player.addItem("—", None)
        for p in self.project.roster: player.addItem(p["name"], p["id"])
        player.setCurrentIndex(max(0, player.findData(event.player_id))); form.addRow("Player", player)
        related = QLineEdit(", ".join(event.related_event_ids)); form.addRow("Related IDs", related)
        related_pick = QComboBox(); related_pick.addItem("Select event to link", None)
        for other in sorted(self.project.events, key=lambda item: item.global_video_time_ms):
            if other.event_id != event.event_id:
                related_pick.addItem(f"{fmt(other.global_video_time_ms)} · {other.type} · {other.event_id[:8]}", other.event_id)
        add_relation = QPushButton("Add link")
        def append_relation():
            picked = related_pick.currentData()
            if picked and picked not in [part.strip() for part in related.text().split(",")]:
                related.setText(", ".join(filter(None, [related.text().strip(), picked])))
        add_relation.clicked.connect(append_relation)
        form.addRow("Link event", related_pick)
        form.addRow("", add_relation)
        attributes = QLineEdit(json.dumps(event.attributes, ensure_ascii=False)); form.addRow("Attributes JSON", attributes)
        actions = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        delete = QPushButton("Delete"); actions.addButton(delete, QDialogButtonBox.DestructiveRole)
        actions.accepted.connect(dialog.accept); actions.rejected.connect(dialog.reject)
        delete.clicked.connect(lambda: dialog.done(2)); form.addRow(actions)
        result = dialog.exec()
        if result == 2:
            self._remember()
            self.project.events.remove(event)
            for other in self.project.events:
                other.related_event_ids = [item for item in other.related_event_ids if item != event.event_id]
            self._changed(); self._refresh_log(); return
        if result != QDialog.Accepted: return
        try:
            payload = json.loads(attributes.text())
            if not isinstance(payload, dict): raise ValueError("Attributes must be an object")
            ids = [s.strip() for s in related.text().split(",") if s.strip()]
            if any(i == event.event_id or not any(e.event_id == i for e in self.project.events) for i in ids):
                raise ValueError("Related IDs must refer to other events")
            self._remember()
            event.note = note.text(); event.team_id = team.currentData(); event.player_id = player.currentData()
            event.related_event_ids = ids; event.attributes = payload; event.validate()
            self._changed(); self._refresh_log()
        except Exception as exc: self._error(str(exc))

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(copy.deepcopy(self.project.events))
            self.project.events = self.undo_stack.pop(); self._changed(); self._refresh_log()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(copy.deepcopy(self.project.events))
            self.project.events = self.redo_stack.pop(); self._changed(); self._refresh_log()

    def _period_changed(self, text):
        if text and text != self.project.period:
            self.project.period = text; self._changed()

    def _clock_toggle(self):
        pos = self._current_time()
        if pos is None: return
        running = not self.project.clock_running
        set_running(self.project, running, pos.global_video_time_ms)
        self._add_event("game_start" if running else "game_stop")
        self._changed()

    def _clock_sync(self):
        pos = self._current_time()
        if pos is None: return
        value, ok = QInputDialog.getText(self, "Sync game clock", "MM:SS.mmm", text=fmt(clock_at(self.project, pos.global_video_time_ms) or 0))
        if not ok: return
        try: value_ms = parse_clock(value)
        except Exception as exc: self._error(str(exc)); return
        original = clock_at(self.project, pos.global_video_time_ms)
        sync_clock(self.project, value_ms, pos.global_video_time_ms)
        self._add_event("clock_sync", attributes={"previous_game_clock_ms": original, "new_game_clock_ms": value_ms})
        self._changed()

    def score_correction(self, kind=None):
        if not self.project.teams: self._error("Add teams to record a score."); return
        if kind not in {"score_snapshot", "score_correction"}:
            kind, ok = QInputDialog.getItem(self, "Score", "Record", ["score_snapshot", "score_correction"], editable=False)
            if not ok: return
        scores = {}
        for team in self.project.teams:
            value, ok = QInputDialog.getInt(self, "Score snapshot", team["name"], 0, 0, 9999)
            if not ok: return
            scores[team["id"]] = value
        self._add_event(kind, attributes={"scores": scores})

    def _toggle_play(self):
        if self.player and self.project.media:
            try: self.player.play_pause()
            except Exception as exc: self._error(str(exc))

    def _skip(self, ms):
        if self.player:
            try:
                self.position = None
                self.player.skip(ms)
            except Exception as exc: self._error(str(exc))

    def _frame(self):
        if self.player: self.player.step_frame()

    def _seek_release(self):
        if self.player:
            try:
                self.position = None
                self.player.seek_global(self.seek.value())
            except Exception as exc: self._error(str(exc))

    def _speed(self, value):
        if self.player: self.player.set_speed(float(value))

    def _volume(self, value):
        if self.player: self.player.set_volume(value)

    def _bind_shortcuts(self):
        for shortcut in self.shortcuts: shortcut.setEnabled(False); shortcut.deleteLater()
        self.shortcuts.clear()
        self.event_shortcuts.clear()
        bindings = {"Space": self._toggle_play, "Left": lambda: self._skip(-5000),
                    "Right": lambda: self._skip(5000), "Ctrl+Z": self.undo, "Ctrl+Y": self.redo,
                    ".": self._frame, "Esc": self._cancel_tag}
        playback_keys = set(bindings)
        for event in events_for_level(self.profile, self.project.level):
            key = self.project.shortcuts.get(event["type"], event.get("key"))
            if key and key not in bindings: bindings[key] = lambda kind=event["type"]: self.tag(kind)
        for sequence, action in bindings.items():
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(action); self.shortcuts.append(shortcut)
            if sequence not in playback_keys:
                self.event_shortcuts.append(shortcut)
                if self.pending_tag is not None:
                    shortcut.setEnabled(False)

    def edit_shortcuts(self):
        labels = [f"{e['type']}: {self.project.shortcuts.get(e['type'], e.get('key', ''))}" for e in events_for_level(self.profile, self.project.level)]
        item, ok = QInputDialog.getItem(self, "Shortcuts", "Choose action", labels, editable=False)
        if not ok: return
        kind = item.split(":", 1)[0]
        value, ok = QInputDialog.getText(self, "Shortcut", "Qt key sequence (e.g. Ctrl+1)", text=self.project.shortcuts.get(kind, ""))
        if not ok: return
        if value and QKeySequence(value).isEmpty(): self._error("Invalid shortcut"); return
        if value:
            normalized = QKeySequence(value).toString()
            reserved = {QKeySequence(key).toString() for key in ("Space", "Left", "Right", "Ctrl+Z", "Ctrl+Y", ".", "Esc", "Return", "Enter")}
            if normalized in reserved:
                self._error("This shortcut is reserved for playback or undo/redo."); return
            for event in events_for_level(self.profile, self.project.level):
                if event["type"] == kind:
                    continue
                other = self.project.shortcuts.get(event["type"], event.get("key"))
                if other and QKeySequence(other).toString() == normalized:
                    self._error(f"This shortcut is already used by {event['type']}."); return
        self.project.shortcuts[kind] = value
        self._changed(); self._refresh_all(); self._bind_shortcuts()

    def export_project(self):
        file, _ = QFileDialog.getSaveFileName(self, "Export events", self.path.with_suffix(".json").name, "JSON (*.json)")
        if file:
            try: export_json(self.project, file, self.path.parent)
            except Exception as exc: self._error(str(exc))

    def export_stats(self):
        file, _ = QFileDialog.getSaveFileName(self, "Export statistics", self.path.with_suffix(".csv").name, "CSV (*.csv)")
        if file:
            try: export_csv(self.project, file)
            except Exception as exc: self._error(str(exc))

    def export_webmaker(self):
        folder = QFileDialog.getExistingDirectory(self, "Select WebMAKER project folder", str(Path.home()))
        if not folder:
            return
        try:
            games = load_webmaker_games(folder)
            labels = [game.label for game in games]
            label, ok = QInputDialog.getItem(self, "WebMAKER statistics", "Choose the match", labels, editable=False)
            if not ok:
                return
            game = games[labels.index(label)]
            file, _ = QFileDialog.getSaveFileName(self, "Export WebMAKER player statistics",
                                                   f"{game.game_id}-stats.csv", "CSV (*.csv)")
            if not file:
                return
            rows, skipped, rebounds = export_webmaker_stats(self.project, game, file)
            QMessageBox.information(self, "WebMAKER export",
                f"Exported {rows} player rows. {skipped} team-only events could not be attributed to a player; "
                f"{rebounds} generic rebounds were not classified as offensive or defensive. "
                "Minutes and unobserved statistics are blank. Import this CSV in WebMAKER Studio's "
                "player statistics section, review the rows, then save the site data.")
        except Exception as exc:
            self._error(f"WebMAKER export failed: {exc}")

    def closeEvent(self, event):
        self.timer.stop()
        self.autosave.stop()
        self.capture_base = None
        self.capture_events = []
        if self.dirty:
            try:
                snapshot = Project.from_dict(self.project.to_dict())
                self.save_future = self.executor.submit(save_project, self.path, snapshot)
            except Exception as exc:
                self.timer.start(100)
                self._error(f"Could not prepare final save: {exc}")
                event.ignore()
                return
        self.executor.shutdown(wait=True)
        try:
            if self.save_future:
                self.save_future.result()
        except Exception as exc:
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tagmaker-save")
            self.timer.start(100)
            self._error(f"Could not save project: {exc}")
            event.ignore()
            return
        self.probe_executor.shutdown(wait=False, cancel_futures=True)
        if self.player: self.player.close()
        event.accept()


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PlayMAKER.TagMAKER")
        except (AttributeError, OSError):
            pass
    application = QApplication(sys.argv)
    application.setWindowIcon(QIcon(str(ICON_PATH)))
    chooser = StartDialog()
    if chooser.exec() != QDialog.Accepted: return 0
    window = MainWindow(chooser.project, chooser.path, chooser.profile_data)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
