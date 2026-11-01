$ErrorActionPreference = "Stop"
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m playwright install chromium
python -m PyInstaller --noconfirm --windowed --name AURA --collect-all PySide6 --collect-all faster_whisper --paths . aura/__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
& "$PSScriptRoot/verify-package.ps1"
Write-Host "Build output: dist/AURA/"
