$ErrorActionPreference = "Stop"
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --windowed --onefile --name Jarvis --collect-all PySide6 --collect-all faster_whisper --collect-data playwright --paths . aura/__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
& "$PSScriptRoot/verify-package.ps1" -Executable dist/Jarvis.exe
Write-Host "Build output: dist/Jarvis.exe"
