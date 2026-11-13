$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$buildOriginalPath = $env:PATH
Push-Location $repoRoot
try {
    # Qt uses Windows ICU. Do not accidentally bundle Poppler's incompatible ICU
    # from a developer tool's PATH into the application.
    $env:PATH = "$repoRoot\.venv\Scripts;$env:SystemRoot\System32;$env:SystemRoot"
    $python = Join-Path $repoRoot '.venv\Scripts\python.exe'
    & $python scripts\collect_licenses.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao coletar licencas.' }
    & $python scripts\make_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar icone.' }
    & $python -m PyInstaller --noconfirm --clean --windowed --onedir --name KardiaOS --icon build/app.ico --paths src --add-data 'LICENSE;.' --add-data 'README.md;.' --add-data 'THIRD_PARTY.md;.' --add-data 'build/licenses;licenses' --add-data 'src/kardiaos/assets;kardiaos/assets' --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module tkinter --exclude-module pytest run.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar executavel.' }
    & $python scripts\stage_source.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar fontes.' }
    $iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    & $iscc installer\KardiaOS.iss
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar instalador.' }
} finally { $env:PATH = $buildOriginalPath; Pop-Location }
