import json
import pytest

from aura import packaging_check


def test_real_voice_assets_load_and_process_silence():
    assert packaging_check.check_voice_assets()["ok"]


def test_missing_asset_directory_is_rejected(tmp_path, monkeypatch):
    import faster_whisper.utils

    monkeypatch.setattr(faster_whisper.utils, "get_assets_path", lambda: str(tmp_path))
    with pytest.raises(RuntimeError, match="Missing Silero ONNX VAD assets"):
        packaging_check.check_voice_assets()


def test_failed_voice_check_writes_failure_report(tmp_path, monkeypatch):
    def missing_asset():
        raise FileNotFoundError("silero_vad_v6.onnx")

    monkeypatch.setattr(packaging_check, "check_voice_assets", missing_asset)
    report = tmp_path / "report.json"
    assert packaging_check.write_voice_check_report(report) == 1
    assert json.loads(report.read_text()) == {
        "ok": False, "error": "silero_vad_v6.onnx"
    }
