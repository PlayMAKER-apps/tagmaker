# Private Windows packaging candidate

`build_windows.ps1` runs tests and makes a one-folder PyInstaller build in
`dist/TagMAKER`. Pass the path to a local `libmpv-2.dll`. The script includes a
visible `PRIVATE_TEST_BUILD.txt` marker; the bundled local test DLL has not
passed the redistribution audit in `docs/licenses.md`. Do not publish this
candidate.

```powershell
.\packaging\build_windows.ps1 -MpvDll .\.local-tools\mpv\libmpv-2.dll
```

If an Inno Setup `ISCC.exe` compiler is available, add `-Iscc C:\path\to\ISCC.exe`
to compile `TagMAKER.iss` into a private per-user installer. Test install,
launch, playback of MP4/MTS, project reopen, and uninstall on a clean Windows
account before a public release. The public package must remove the private
marker, include complete third-party notices and source access, and use a DLL
whose exact build has been audited. Code signing is also recommended for a
downloadable installer.
