param(
    [Parameter(Mandatory = $true)][string]$MpvDll,
    [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dll = (Resolve-Path -LiteralPath $MpvDll).Path
if ([IO.Path]::GetFileName($dll) -ne "libmpv-2.dll") {
    throw "Select a libmpv-2.dll file"
}
$python = Join-Path $repo ".venv-uv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Install TagMAKER and PyInstaller in .venv-uv before packaging"
}

Push-Location $repo
try {
    & $python -m pytest -q --basetemp .pytest-temp
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    & $python -m PyInstaller --noconfirm --onedir --windowed `
        --contents-directory . --name TagMAKER --specpath build `
        --icon (Join-Path $repo "app\assets\tagmaker.ico") `
        --add-data "$(Join-Path $repo 'profiles');profiles" `
        --add-data "$(Join-Path $repo 'app\assets\tagmaker.ico');app\assets" `
        --add-binary "$dll;." `
        "app\main.py"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    Copy-Item -LiteralPath "LICENSE" -Destination "dist\TagMAKER\LICENSE.txt" -Force
    Copy-Item -LiteralPath "README.md" -Destination "dist\TagMAKER\README.md" -Force
    Copy-Item -LiteralPath "docs\licenses.md" -Destination "dist\TagMAKER\THIRD_PARTY_REVIEW.md" -Force
    "PRIVATE TEST BUILD - NOT CLEARED FOR DISTRIBUTION" |
        Set-Content -LiteralPath "dist\TagMAKER\PRIVATE_TEST_BUILD.txt" -Encoding utf8
    if ($Iscc) {
        & $Iscc "packaging\TagMAKER.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed" }
    }
} finally {
    Pop-Location
}
