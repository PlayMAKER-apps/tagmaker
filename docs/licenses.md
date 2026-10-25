# Licenses and distribution audit

TagMAKER source is GPL-3.0-or-later; see [LICENSE](../LICENSE). The implementation uses Python's standard library, PySide6 Essentials, `python-mpv`, PyYAML, and a user-provided libmpv binary.

| Component | License information | Distribution action |
| --- | --- | --- |
| TagMAKER | GPL-3.0-or-later | Include source and LICENSE. |
| Qt for Python / PySide6 Essentials | LGPLv3/GPLv3 or commercial options according to [Qt documentation](https://doc.qt.io/qtforpython-6/) | Preserve Qt notices and library replacement rights when redistributing binaries. |
| python-mpv | Source repository provides [LGPL and GPL license files](https://github.com/jaseg/python-mpv) | Verify the exact package release metadata and notices for a binary distribution. |
| PyYAML | The installed 6.0.3 package declares MIT in its package metadata. | Include the version's license notice when redistributing. |
| Python runtime | [PSF License Version 2](https://docs.python.org/3.12/license.html), with incorporated third-party components | Include matching Python license and applicable incorporated-component notices for a frozen build. |
| PyInstaller bootloader | [GPL-2.0-or-later with a bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt) | Include the exact version's notices in the release audit. |
| Inno Setup compiler | [Inno Setup terms](https://jrsoftware.org/isinfo.php), with [commercial licensing guidance](https://jrsoftware.org/isorder.php) | Clarify intended commercial/non-commercial use before adopting the compiler for production. |
| libmpv / mpv | [mpv Copyright](https://github.com/mpv-player/mpv/blob/master/Copyright) says GPLv2+ by default; LGPLv2.1+ is possible only for an audited build without GPL-only sources. `-Dgpl=false` alone is not a blanket license grant. Linked FFmpeg libraries can affect the result. | Record the exact DLL and FFmpeg build provenance, licenses, source availability and notices. Do not call an unverified DLL LGPL. |

## Exact local test binary (25 October 2026)

The local test archive is the [shinchiro 2026-10-21 x86-64 development build](https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261021), archive SHA-256 `efc719eff3dc5954b4a5efc800632808bcec01cc9034940dd14e5eb7fe9ea633`. The extracted `libmpv-2.dll` SHA-256 is `04e4d27dc385dc18ddd93fbe69c75e635b864f3c6ec53a9122df54c2f7842f4a`. The archive contains the DLL, an import library, and headers; it does **not** contain license notices, component manifests, build configuration, or corresponding FFmpeg/mpv source. It is suitable for local testing, but these missing materials prevent a complete redistribution audit from the archive alone. The local Python packages are PySide6-Essentials 6.12.0, python-mpv 1.0.8, and PyYAML 6.0.3.

The [mpv copyright file](https://github.com/mpv-player/mpv/blob/master/Copyright) says mpv is GPLv2+ by default and only an audited GPL-free build can be LGPLv2.1+. [FFmpeg's legal page](https://ffmpeg.org/legal.html) says optional GPL parts can change FFmpeg's license and calls for matching source, build configuration, and notices for distribution. [Qt for Python](https://doc.qt.io/qtforpython-6/) lists LGPLv3/GPLv3 and commercial terms, plus [third-party notices](https://doc.qt.io/qtforpython-6/licenses.html). The GPL-3.0-or-later TagMAKER source does not by itself supply the missing notices and source for bundled binaries.

The repository does **not** track a DLL, FFmpeg, an installer, or a portable zip. A locally built, ignored private installer candidate may exist under `dist/`; it is marked `PRIVATE TEST BUILD` and is not a release artifact. Before public packaging, select a binary with clear licensing and build provenance; pin every version and hash; inspect linked components; include the applicable notices, license texts, and corresponding source access; then test the packaged application and library replacement where required. Until that audit is complete, a public installer must not bundle the local test DLL.
