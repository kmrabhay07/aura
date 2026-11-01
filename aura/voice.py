"""Activated audio capture, reusable offline recognition, and serial local speech."""
import queue
import sys
import threading
import time


class Recorder:
    RATE = 16000

    def __init__(self, stream_factory=None, max_seconds=120):
        self.stream_factory = stream_factory
        self.max_seconds = max_seconds
        self.device = None
        self._lock = threading.Lock()

    def capture(self, turn, listening=lambda: None):
        import numpy as np
        factory = self.stream_factory
        if factory is None:
            import sounddevice as sd
            factory = sd.InputStream
        with self._lock:
            turn.check()
            if turn.released.is_set():
                return np.zeros(0, dtype=np.float32), False
            chunks = []
            samples = 0
            errors = []
            limit = int(self.RATE * self.max_seconds)

            def receive(data, frames, timing, status):
                nonlocal samples
                if status:
                    errors.append("Microphone overflow or device error; try again")
                    turn.released.set()
                if turn.cancel.is_set() or turn.released.is_set():
                    return
                chunk = data[:max(0, limit - samples), 0].copy()
                chunks.append(chunk)
                samples += len(chunk)
                if samples >= limit:
                    turn.released.set()

            started = time.monotonic()
            options = dict(samplerate=self.RATE,channels=1,dtype='float32',callback=receive)
            if self.device is not None:
                options['device'] = self.device
            with factory(**options):
                listening()
                # Release during device startup is remembered. The microphone
                # is opened only in this explicitly activated scope.
                turn.released.wait(self.max_seconds)
            turn.check()
            if errors:
                raise RuntimeError(errors[0])
            capped = samples >= limit or time.monotonic() - started >= self.max_seconds
            return (np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32), capped)


class Transcriber:
    def __init__(self, model_factory=None, model_size="base"):
        self.factory = model_factory
        self.model_size = model_size
        self._model = None
        self._lock = threading.Lock()

    def transcribe(self, audio, turn):
        if len(audio) < 1600:
            return ""
        # Native inference is serialized. Cancellation discards its result;
        # it cannot forcibly interrupt a model load or native inference call.
        with self._lock:
            turn.check()
            if self._model is None:
                factory = self.factory
                if factory is None:
                    from faster_whisper import WhisperModel
                    factory = WhisperModel
                self._model = factory(self.model_size, device="cpu", compute_type="int8")
            turn.check()
            segments, _ = self._model.transcribe(audio, vad_filter=True, beam_size=1)
            text = []
            for segment in segments:
                turn.check()
                text.append(segment.text.strip())
            turn.check()
            return " ".join(text).strip()


class Speaker:
    """One engine on one owning thread, with cancellable external event pumping."""
    def __init__(self, notify=lambda turn, state, detail: None, engine_factory=None):
        self.notify = notify
        self.engine_factory = engine_factory
        self._queue = queue.Queue(maxsize=128)
        self._closed = threading.Event()
        self._quiet = threading.Event()
        self._quiet.set()
        self._unsafe = False
        self._options = ('',0)
        self._thread = threading.Thread(target=self._run, daemon=True, name="Jarvis speech")
        self._thread.start()

    def configure(self, voice='', rate=200):
        self._options = (str(voice),max(100,min(300,int(rate))))

    def _enqueue(self, turn, text):
        while not self._closed.is_set():
            turn.check()
            try:
                self._queue.put((turn, text), timeout=0.05)
                return
            except queue.Full:
                continue
        from .conversation import Cancelled
        raise Cancelled()

    def say(self, turn, text):
        self._enqueue(turn, text)

    def finish(self, turn):
        self._enqueue(turn, None)

    def wait_quiet(self, timeout=2):
        return self._quiet.wait(timeout) and not self._unsafe

    def close(self):
        self._closed.set()

    def _run(self):
        engine = None
        com = None
        failed_turns = set()
        applied_options = None
        try:
            while not self._closed.is_set():
                try:
                    turn, text = self._queue.get(timeout=0.02)
                except queue.Empty:
                    continue
                if turn.cancel.is_set():
                    continue
                if text is None:
                    self.notify(turn, "speech_done", "")
                    failed_turns.discard(turn.number)
                    continue
                if turn.number in failed_turns:
                    continue
                if self._unsafe:
                    self.notify(turn, "speech_error", "Speech driver could not stop; restart Jarvis before using voice")
                    failed_turns.add(turn.number)
                    continue
                self._quiet.clear()
                try:
                    if engine is None:
                        if sys.platform == "win32" and self.engine_factory is None and com is None:
                            import pythoncom
                            pythoncom.CoInitialize()
                            com = pythoncom
                        factory = self.engine_factory
                        if factory is None:
                            import pyttsx3
                            factory = pyttsx3.init
                        engine = factory()
                        engine.startLoop(False)
                        engine.iterate()
                    if turn.cancel.is_set():
                        continue
                    options = self._options
                    if options != applied_options:
                        if options[0]:
                            engine.setProperty('voice',options[0])
                        if options[1]:
                            engine.setProperty('rate',options[1])
                        applied_options = options
                    self.notify(turn, "speaking", "")
                    engine.say(text)
                    while engine.isBusy():
                        engine.iterate()
                        if turn.cancel.is_set() or self._closed.is_set():
                            engine.stop()
                            deadline = time.monotonic() + 1
                            while engine.isBusy() and time.monotonic() < deadline:
                                engine.iterate()
                                time.sleep(0.01)
                            if engine.isBusy():
                                self._unsafe = True
                                raise RuntimeError("Speech driver did not stop")
                            break
                        time.sleep(0.01)
                except Exception:
                    failed_turns.add(turn.number)
                    self.notify(turn, "speech_error", "Local speech failed; text replies remain available")
                    if engine:
                        try:
                            engine.stop()
                            if engine.isBusy():
                                self._unsafe = True
                            engine.endLoop()
                        except Exception:
                            self._unsafe = True
                    engine = None
                    applied_options = None
                finally:
                    self._quiet.set()
        finally:
            if engine:
                try:
                    engine.stop()
                    engine.endLoop()
                except Exception:
                    pass
            self._quiet.set()
            if com:
                com.CoUninitialize()


def installed_voices():
    if sys.platform != 'win32':
        return []
    import winreg
    voices = []
    base = r'SOFTWARE\Microsoft\Speech\Voices\Tokens'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,base) as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                token = winreg.EnumKey(root,i)
                with winreg.OpenKey(root,token) as key:
                    label = winreg.QueryValue(key,None)
                voices.append((str(label),'HKEY_LOCAL_MACHINE\\'+base+'\\'+token))
    except OSError:
        pass
    return voices


def input_devices():
    try:
        import sounddevice as sd
        return [(str(d['name']),i) for i,d in enumerate(sd.query_devices()) if d['max_input_channels']>0]
    except Exception:
        return []
