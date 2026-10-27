# Third-party software in the Windows test build

This file identifies components shipped with the PyInstaller one-folder build.
TagMAKER itself is GPL-3.0-or-later; see `LICENSE.txt`. This inventory is
version-specific and must be reviewed when rebuilding with changed packages.
The external-libmpv build contains **no libmpv or FFmpeg binary**. Users obtain
and select `libmpv-2.dll` separately; its licensing depends on that DLL's build.

| Shipped component | Version | License and included text | Corresponding source |
| --- | --- | --- | --- |
| CPython and standard library | 3.12.14 | `licenses/Python-3.12.txt` | [CPython v3.12.14](https://github.com/python/cpython/tree/v3.12.14) |
| OpenSSL DLLs from the CPython runtime | 3.5.8 | Apache-2.0; `licenses/OpenSSL-Apache-2.0.txt` | [OpenSSL 3.5.8](https://github.com/openssl/openssl/tree/openssl-3.5.8) |
| Qt Core, GUI, Network, Widgets, SVG and plugins | 6.12.0 | LGPL-3.0-only or GPL-3.0-only (GPLv3 selected for this GPL application); `licenses/Qt-LGPL-3.0-only.txt` and `LICENSE.txt` | [Qt 6.12.0 source packages](https://www.qt.io/development/offline-installers), [Qt third-party attributions](https://doc.qt.io/qt-6/licenses-used-in-qt.html) |
| PySide6 Essentials and Shiboken6 | 6.12.0 | LGPL-3.0-only or GPL-3.0-only (GPLv3 selected); same texts as above | [PySide source, v6.12.0](https://github.com/pyside/pyside-setup/tree/v6.12.0) |
| python-mpv | 1.0.8 | LGPL-2.1-or-later or GPL-2.0-or-later; `licenses/python-mpv-LGPL.txt` and `licenses/python-mpv-GPL.txt` | [python-mpv 1.0.8](https://pypi.org/project/python-mpv/1.0.8/#files) |
| PyYAML | 6.0.3 | MIT; `licenses/PyYAML-MIT.txt` | [PyYAML 6.0.3](https://pypi.org/project/PyYAML/6.0.3/#files) |
| PyInstaller bootloader | 6.22.3 | GPL-2.0-or-later with bootloader exception; `licenses/PyInstaller-COPYING.txt` | [PyInstaller v6.22.3](https://github.com/pyinstaller/pyinstaller/tree/v6.22.3) |
| Inno Setup installer engine | 6.7.3 | Inno Setup License; `licenses/Inno-Setup.txt` in the installed app | [Inno Setup](https://jrsoftware.org/isinfo.php) |
| Microsoft Visual C++ runtime DLLs carried by Python/PySide wheels | versions vary by file | Redistribution terms and provenance still require review | [Microsoft redistribution guidance](https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files) |
| libffi DLL carried by the Python runtime | exact build unverified | MIT-style upstream terms require notice review | [libffi source](https://github.com/libffi/libffi) |

The Qt libraries and plugins are separate DLLs under `PySide6/`. Recipients
can replace them with compatible builds. See [Qt's LGPL guidance](https://doc.qt.io/qt-6/licensing.html),
[Qt's third-party attributions](https://doc.qt.io/qt-6/licenses-used-in-qt.html),
and the [Qt 6.12.0 source package links](https://www.qt.io/development/offline-installers).
The Python binding extensions, Microsoft runtime DLLs, and libffi build need
separate provenance and redistribution review before this test build is
published. The upstream links above do not by themselves establish that the
source matches every shipped binary.
