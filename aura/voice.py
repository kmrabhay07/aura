"""Push-to-talk voice capture and offline speech recognition."""
from pathlib import Path
import tempfile
import wave

def transcribe_once(seconds=6, model_size="base"):
    """Record a short utterance; microphone access is initiated by the user."""
    import sounddevice as sd
    from faster_whisper import WhisperModel

    rate = 16000
    audio = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="int16")
    sd.wait()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "speech.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(audio.tobytes())
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path), vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()

def speak(text):
    """Optional local text-to-speech; not enabled automatically."""
    import pyttsx3
    engine = pyttsx3.init()
    engine.say(text[:1200])
    engine.runAndWait()
