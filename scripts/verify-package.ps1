param([string]$PackagePath = "dist/AURA", [string]$Executable)
$ErrorActionPreference = "Stop"
if ($Executable) {
    $exe = $Executable
} else {
    $exe = Join-Path $PackagePath "AURA.exe"
    $assets = Join-Path $PackagePath "_internal/faster_whisper/assets"
    if (!(Test-Path "$assets/silero*.onnx")) { throw "Packaged Silero VAD assets missing: $assets" }
    # PyInstaller requires _internal/base_library.zip; only reject wrapper archives.
    if (Get-ChildItem $PackagePath -File -Filter *.zip) { throw "Wrapper ZIP found at application root" }
}
if (!(Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Executable missing: $exe" }
$report = Join-Path ([IO.Path]::GetTempPath()) ("aura-voice-" + [guid]::NewGuid() + ".json")
try {
    $process = Start-Process -FilePath (Resolve-Path $exe) -ArgumentList @("--verify-voice-assets", "`"$report`"") -WindowStyle Hidden -PassThru
    if (!$process.WaitForExit(120000)) {
        $process.Kill()
        throw "Packaged voice check timed out"
    }
    if ($process.ExitCode -ne 0 -or !(Test-Path $report)) { throw "Packaged voice check failed (exit $($process.ExitCode))" }
    $result = Get-Content $report -Raw | ConvertFrom-Json
    if ($result.ok -ne $true) { throw "Packaged voice check failed: $($result.error)" }
    Write-Host "Packaged VAD loaded and processed silence: $($result.assets)"
} finally {
    if (Test-Path $report) { Remove-Item -LiteralPath $report }
}
