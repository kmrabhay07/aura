$ErrorActionPreference = "Stop"
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m playwright install chromium
python -m PyInstaller --noconfirm --windowed --name AURA --collect-all PySide6 --collect-all faster_whisper aura/main.py
Write-Host "Build output: dist/AURA/"
