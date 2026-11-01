param([string]$PackagePath = "dist/AURA")
$ErrorActionPreference = "Stop"
$exe = Join-Path $PackagePath "AURA.exe"
if (!(Test-Path $exe)) { throw "AURA.exe missing" }
$assets = Join-Path $PackagePath "_internal/faster_whisper/assets"
if (!(Test-Path "$assets/silero*.onnx")) { throw "Packaged Silero VAD assets missing: $assets" }
if (Get-ChildItem $PackagePath -Recurse -Filter *.zip) { throw "Nested ZIP found in application package" }
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
