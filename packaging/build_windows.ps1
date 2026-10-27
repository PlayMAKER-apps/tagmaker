param(
    [string]$MpvDll = "",
    [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dll = if ($MpvDll) { (Resolve-Path -LiteralPath $MpvDll).Path } else { $null }
if ($dll -and [IO.Path]::GetFileName($dll) -ne "libmpv-2.dll") {
    throw "Select a libmpv-2.dll file"
}
$python = Join-Path $repo ".venv-uv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Install TagMAKER and PyInstaller in .venv-uv before packaging"
}
$pythonBase = (& $python -c "import sys; print(sys.base_prefix)").Trim()
if (-not (Test-Path -LiteralPath (Join-Path $pythonBase "python312.dll"))) {
    throw "Cannot locate the base Python runtime"
}
& $python -c "import sys, ssl; from importlib.metadata import version; assert sys.version_info[:3] == (3, 12, 14); assert ssl.OPENSSL_VERSION.startswith('OpenSSL 3.5.8 '); assert all(version(name) == expected for name, expected in [('PySide6_Essentials', '6.12.0'), ('shiboken6', '6.12.0'), ('python-mpv', '1.0.8'), ('PyYAML', '6.0.3'), ('PyInstaller', '6.22.3')])"
if ($LASTEXITCODE -ne 0) { throw "Packaging dependency versions differ from third-party notices" }

Push-Location $repo
try {
    & $python -m pytest -q --basetemp .pytest-temp
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    # PyInstaller searches PATH for transitive DLLs. Restrict it to this Python
    # runtime and Windows so Codex/Poppler/libheif tools cannot contaminate Qt.
    $previousPath = $env:PATH
    try {
        $env:PATH = @((Join-Path $repo ".venv-uv\Scripts"), $pythonBase,
                      (Join-Path $pythonBase "DLLs"),
                      (Join-Path $env:SystemRoot "System32"), $env:SystemRoot) -join ";"
        $mpvBinaryArg = if ($dll) { @("--add-binary", "$dll;.") } else { @() }
        & $python -m PyInstaller --noconfirm --onedir --windowed `
            --contents-directory . --name TagMAKER --specpath build `
            --icon (Join-Path $repo "app\assets\tagmaker.ico") `
            --add-data "$(Join-Path $repo 'profiles');profiles" `
            --add-data "$(Join-Path $repo 'app\assets\tagmaker.ico');app\assets" `
            --add-data "$(Join-Path $repo 'app\assets\tagmaker-file.ico');app\assets" `
            @mpvBinaryArg `
            "app\main.py"
    } finally {
        $env:PATH = $previousPath
    }
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    $provenanceArgs = @("packaging\check_binary_provenance.py", "build\TagMAKER\Analysis-00.toc",
                        (Join-Path $repo ".venv-uv"), $pythonBase)
    if ($dll) { $provenanceArgs += $dll }
    & $python @provenanceArgs
    if ($LASTEXITCODE -ne 0) { throw "Unexpected PyInstaller binary source" }
    # Qt 6 on Windows imports the system ICU's unversioned symbols. PyInstaller
    # can pick up Codex's Poppler ICU from PATH; that DLL exports versioned
    # symbols instead and makes the frozen QtCore import fail at startup.
    foreach ($foreignIcu in @("icuuc.dll", "icudt78.dll", "icuin.dll")) {
        $candidate = Join-Path $repo "dist\TagMAKER\$foreignIcu"
        if (Test-Path -LiteralPath $candidate) {
            Remove-Item -LiteralPath $candidate -Force
        }
    }
    Copy-Item -LiteralPath "LICENSE" -Destination "dist\TagMAKER\LICENSE.txt" -Force
    Copy-Item -LiteralPath "README.md" -Destination "dist\TagMAKER\README.md" -Force
    Copy-Item -LiteralPath "docs\licenses.md" -Destination "dist\TagMAKER\THIRD_PARTY_REVIEW.md" -Force
    Copy-Item -LiteralPath "packaging\THIRD_PARTY_NOTICES.md" -Destination "dist\TagMAKER\THIRD_PARTY_NOTICES.md" -Force
    $licenseDest = Join-Path $repo "dist\TagMAKER\licenses"
    New-Item -ItemType Directory -Path $licenseDest -Force | Out-Null
    $sitePackages = Join-Path $repo ".venv-uv\Lib\site-packages"
    $licenseSources = @{
        "Python-3.12.txt" = (Join-Path $pythonBase "LICENSE.txt")
        "PyInstaller-COPYING.txt" = (Join-Path $sitePackages "pyinstaller-6.22.3.dist-info\licenses\COPYING.txt")
        "PyYAML-MIT.txt" = (Join-Path $sitePackages "pyyaml-6.0.3.dist-info\licenses\LICENSE")
        "python-mpv-GPL.txt" = (Join-Path $sitePackages "python_mpv-1.0.8.dist-info\licenses\LICENSE.GPL")
        "python-mpv-LGPL.txt" = (Join-Path $sitePackages "python_mpv-1.0.8.dist-info\licenses\LICENSE.LGPL")
        "OpenSSL-Apache-2.0.txt" = (Join-Path $repo "packaging\licenses\OpenSSL-Apache-2.0.txt")
        "Qt-LGPL-3.0-only.txt" = (Join-Path $repo "packaging\licenses\Qt-LGPL-3.0-only.txt")
        "Inno-Setup.txt" = (Join-Path $repo "packaging\licenses\Inno-Setup.txt")
    }
    foreach ($name in $licenseSources.Keys) {
        Copy-Item -LiteralPath $licenseSources[$name] -Destination (Join-Path $licenseDest $name) -Force
    }
    "PRIVATE TEST BUILD - NOT CLEARED FOR DISTRIBUTION" |
        Set-Content -LiteralPath "dist\TagMAKER\PRIVATE_TEST_BUILD.txt" -Encoding utf8
    if (-not $dll) {
        "Video playback requires a separately supplied libmpv-2.dll. Open TagMAKER and choose Configure libmpv. See README.md." |
            Set-Content -LiteralPath "dist\TagMAKER\EXTERNAL_LIBMPV_REQUIRED.txt" -Encoding utf8
    }
    if ($Iscc) {
        & $Iscc "packaging\TagMAKER.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed" }
    }
} finally {
    Pop-Location
}
