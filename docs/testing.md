# Verification and benchmark record

Automated tests cover clip-boundary arithmetic, explicit milliseconds, manual clock stop/sync, SQLite reopen, JSON round trip, CSV aggregation, schema rejection, separate sport profiles, custom profile portability, the two-step Qt tagging flow (jersey number and team-only opponent) with frozen event time and undo/redo, a 10,000-event autosave that yields to the event loop, WebMAKER roster import, and convocati selection. Windows CI is configured to run these tests with the declared dependencies.

An anonymized read of a user-supplied basketball quarter found 43 saved events, 11 called-up players, and 10 legacy one-player substitution tags. The project loads under the updated model and passes the shared JSON Schema validator. A disposable copy populated the new Box score page with 11 player rows and flagged those legacy substitutions; the source quarter file was not changed. This is a useful first alpha usability sample, but it is not a full-match or clean-installer test.

## Real video test procedure

Use a modest Windows 10/11 x64 PC and a locally licensed 1080p recording lasting at least 90 minutes. Also use two consecutive clips with a visible boundary, a VFR file if available, a corrupt file, and a moved/missing file. Record CPU model, RAM, GPU, OS, libmpv DLL source/version, video codec/container/duration, and whether hardware decoding engaged. Measure startup-to-first-frame, seek latency at several positions, time to change clips, UI input response during playback and saving, RAM after 10/60/90 minutes, and SQLite save latency with at least 10,000 events. Check that event source/global/game times are correct around clip boundaries, and that reopen after forced termination retains the last completed save.

## Local integration evidence (24 October 2026)

On this Windows machine, ten automated tests passed. A native Qt/libmpv smoke test used two locally generated 640×360 H.264 clips, 2 seconds each. It reported durations of 2,000 ms each, advanced automatically into the second clip, and read a 2,567 ms global position. The full TagMAKER window recorded one scoring tag during playback, saved it, and reopened the database with the event intact. A separate exact seek to global 2,500 ms resolved to clip 2 at source 500 ms. The test DLL came from the [shinchiro 2026-10-21 x86-64 dev build](https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261021): the downloaded archive SHA-256 is `efc719eff3dc5954b4a5efc800632808bcec01cc9034940dd14e5eb7fe9ea633` and the extracted `libmpv-2.dll` SHA-256 is `04e4d27dc385dc18ddd93fbe69c75e635b864f3c6ec53a9122df54c2f7842f4a`. It was used locally and is not distributed with TagMAKER. Repeating the full window test after the autosave and timestamp changes also passed, with a reported global position of 2,533 ms.

One local SQLite run with 10,000 synthetic events took 481.3 ms to serialize and commit, and 318.5 ms to reopen and validate. The GUI copies event snapshots in 200-event turns through the Qt event loop and writes SQLite on a dedicated worker. These are single-run timings on this development machine, not latency guarantees.

The short synthetic smoke tests verify integration and timestamp mapping, not sustained playback, seek latency, RAM, or responsiveness targets for long recordings.

## Roster and layout verification (25 October 2026)

Thirteen automated tests passed at that revision. The new tests covered WebMAKER CSV/YAML roster loading, jersey number `0`, inactive players, the full GUI import action, reimport without changing TagMAKER player IDs, and convocati selection. A read-only import of the local `Basketball_Team_Tracker` source found 51 roster memberships across three season/team groups. At the default 1280 × 800 window size, the basketball ADVANCED tag grid had no vertical scroll, and Qt loaded the supplied `.ico` successfully. A rebuilt wheel contained the icon and new importer; the native Windows playback/tagging smoke test still passed.

At that revision, the tag buttons had a fixed 34 px height and 4 px vertical gap in the native Windows layout. The GUI test checked that adjacent rows had no more than 6 px of space and that the tag panel did not scroll at its default size. Tutorial screenshots were captured from the actual Qt application using synthetic roster data and a locally generated clip; no external match footage is included.

## Real 1080p video and MTS sampling (25 October 2026)

The user's full `exp.mp4` is 21,050,976,086 bytes, H.264/AAC, 1920×1080 at a reported 25 fps, and 4,303.296 seconds (71 min 43.296 s). A source `00182.MTS` is 2,238,984,192 bytes, MPEG-TS with H.264/AC-3 and subtitle streams, 1920×1080, and 1,041.600 seconds (17 min 21.6 s). Both were read in place; no video was copied into the repository. The MTS failure in the UI was caused by a missing file-dialog extension filter, not by libmpv decoding. The picker now includes `.mts` and `.m2ts` in both cases. A real-file startup also exposed an immediate seek-to-zero that libmpv could reject while opening a large clip; opening at zero now skips that seek.

`tools/benchmark_video.py` drove a native 640×360 Qt/libmpv widget, sampled three exact seeks, eight seconds of playback, and Windows process working-set RAM. The results below are **single-run, warm-system samples**. Startup ends when libmpv exposes video parameters and a position; seek timing ends when libmpv reports the requested position, which can precede presentation of the decoded frame. Neither is a first-visible-frame or decoded-frame latency measurement.

| Clip | Startup to reported position | Seeks at 10/50/90% | Working set after load / playback | Position advanced during 8 s playback |
| --- | ---: | ---: | ---: | ---: |
| MP4, 71:43 | 3,475 ms | 12 / 52 / 67 ms | 220.5 / 260.0 MiB | 7,034 ms |
| MTS, 17:21 | 2,565 ms | 16 / 101 / 12 ms | 234.5 / 263.2 MiB | 7,320 ms |

The test used Windows NT 10.0.26200.0 and the local DLL identified above. Working-set numbers include Python, Qt, and libmpv in the same process and cannot be attributed to one component. Reopening the full MP4 at 2,151,648 ms also succeeded; libmpv reported 2,151,680 ms after the deferred seek. The available complete MP4 is shorter than the planned 90-minute test. Sustained full-match playback, recovery after forced termination, VFR behavior, modest-PC performance, and real annotator feedback remain unverified. Seventeen automated tests passed at that revision, including the shared JSON Schema fixture when the sibling `playmaker-schema` folder is present, WebMAKER per-game statistics and export GUI action, and the MTS picker filter.

## Lineup, substitutions, box score, and executable (25 October 2026)

Nineteen TagMAKER automated tests and six shared-schema tests passed before the final packaging run. The new GUI tests exercise an exact five-player starting lineup, two different players on a substitution, the timestamp retained through both selections, persistence after reopening, the player box score, and the absence of basketball clock controls and period/game buttons in BASIC. At 1280 × 800, the ADVANCED event grid still needs no scrollbar and the event history is 170–260 px high; tag buttons are 31 px high with a 3 px row gap. The tutorial now has eight screenshots, including the new lineup and box score pages.

The user's first tagged quarter contains 43 events, 11 called-up players, and 10 one-player substitution tags made with the old workflow. Its JSON passes the updated shared validator. A disposable database copy populated 11 box score rows; the original file was not changed. The earlier substitutions cannot be paired automatically because they contain no incoming player ID.

The previously packaged `icuuc.dll` came from Codex's Poppler utilities and exports ICU 78-suffixed names; the packaged `Qt6Core.dll` imports unversioned ICU names. The build now removes that incompatible copy and lets Qt load Windows ICU. The rebuilt one-folder EXE remained running after six seconds in an offscreen startup check. This is a startup check, not a clean-machine or full-media packaged playback check.

## Private installer candidate (25 October 2026)

PyInstaller 6.22.3 created a one-folder Windows application. An initial packaging inspection found missing sport profiles and icon data; `packaging/build_windows.ps1` now includes those resources automatically. Inno Setup 6.7.3 compiled a workspace-local `dist/TagMAKER-0.1.0-private-test-setup.exe`; its current hash is recorded below. The candidate is ignored by Git and explicitly marked `PRIVATE TEST BUILD - NOT CLEARED FOR DISTRIBUTION`.

For the preceding build (SHA-256 `9a9d69e6dc9c672462ba2c1619f5928697eeedd7f214def186b7e55e9cdfa335`), a silent per-user install into `.local-tools/installed-test` returned exit code 0 and produced the EXE, libmpv DLL, sport profiles, icon, and uninstaller. The installed EXE stayed running through a seven-second offscreen startup check. The silent uninstaller returned exit code 0 and removed the test installation. The Windows UI automation request timed out, so this pass does **not** establish that the packaged UI can tag an MP4/MTS clip; native source playback and tagging tests cover those flows separately. A clean-machine GUI playback test and complete binary-license audit are release gates.

The two-step tagging update rebuilt a preceding private installer on 25 October 2026 (102,489,621 bytes, SHA-256 `6411da980235bfade2f74320691e46b672fbf4bef9f37332c01db30cbe5d0f56`). Its one-folder packaged EXE remained running through a seven-second offscreen startup check. A silent install attempt with that rebuild inside the restricted Codex workspace failed with exit code 4: the sandbox denied writing the Start Menu shortcut and `HKEY_CURRENT_USER` uninstall key. Inno Setup rolled back the test installation. The normal Windows install/uninstall cycle was then tested with the final candidate below.

## Final private alpha candidate (25 October 2026)

The latest candidate is `dist/TagMAKER-0.1.0-private-alpha-20261025-3.exe`, 88,965,809 bytes, SHA-256 `f2e221f26aa7781d193a93696ba31e9a73dd73b0cca901dcbc97fd40dd67c91a`. Nineteen TagMAKER tests and six shared-schema tests pass. Its one-folder EXE has no bundled Poppler ICU DLL, includes `app/assets/tagmaker-file.ico`, and remained running after opening a synthetic `.tagmaker` project by command-line argument in a normal Qt startup check.

The installer ran silently with per-user Windows permissions and returned exit code 0. The installed folder contained the EXE and grayscale icon. The current-user `.tagmaker` association pointed to the installed EXE with the project path argument, and the installed EXE remained running after opening the synthetic project. The silent uninstaller returned exit code 0, removed the installed EXE, and removed the current-user association. The test installation was under ignored `.local-tools` and has been removed. A prior attempt in the restricted workspace session failed at Start Menu creation; that was a sandbox permission error, not an installer compile or Qt startup failure.

This verifies basic install, launch, file association, and uninstall on this development Windows account. It does not verify another Windows PC/account, packaged MP4/MTS playback, sustained full-match use, or the third-party redistribution audit. The candidate remains an ignored private local test build and is not a public release artifact.
