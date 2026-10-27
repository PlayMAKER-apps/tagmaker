# Windows packaging

`build_windows.ps1` runs tests, builds the one-folder application, and checks
the origin of every native binary selected by PyInstaller. The default build
does not bundle libmpv. Users select a separately obtained `libmpv-2.dll`
from **Configure libmpv** in the application and keep it at that path.

```powershell
.\packaging\build_windows.ps1 -Iscc .\.local-tools\InnoSetup\ISCC.exe
```

`-MpvDll C:\path\to\libmpv-2.dll` is retained for local testing only. Such a
build is marked `PRIVATE TEST BUILD` and must not be uploaded: the local DLL's
source and notices are incomplete. See the [distribution audit](../docs/licenses.md).

The installer registers `.tagmaker` with a grayscale project icon and does
not change the `.sqlite3` association. Before publishing an external-libmpv
installer, review third-party notices and exact source links, test install,
launch, project reopen, playback with a user-selected DLL, and uninstall on a
clean Windows account. Code signing is recommended.
