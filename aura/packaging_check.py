"""Offline smoke check shared by source tests and the frozen executable."""
import json
from pathlib import Path


def check_voice_assets():
    import numpy as np
    from faster_whisper.utils import get_assets_path
    from faster_whisper.vad import get_speech_timestamps

    assets = Path(get_assets_path())
    models = list(assets.glob("silero*.onnx"))
    if not models or any(model.stat().st_size == 0 for model in models):
        raise RuntimeError(f"Missing Silero ONNX VAD assets in {assets}")
    # Exercises faster-whisper's own path resolution and ONNX Runtime loading,
    # without a microphone, network access, or a downloaded Whisper model.
    segments = get_speech_timestamps(np.zeros(16000, dtype=np.float32))
    if segments:
        raise RuntimeError("VAD unexpectedly detected speech in silence")
    return {"ok": True, "assets": [str(model) for model in models]}


def check_browser_runtime():
    import os
    import playwright
    driver = Path(playwright.__file__).resolve().parent / 'driver'
    node = driver / ('node.exe' if os.name=='nt' else 'node')
    cli = driver / 'package' / 'cli.js'
    if not node.is_file() or not cli.is_file():
        raise RuntimeError('Packaged browser driver assets are missing')
    return {'node':str(node),'cli':str(cli)}


def write_voice_check_report(destination):
    try:
        report = check_voice_assets()
        report['browser_runtime'] = check_browser_runtime()
    except Exception as exc:
        Path(destination).write_text(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    Path(destination).write_text(json.dumps(report))
    return 0
