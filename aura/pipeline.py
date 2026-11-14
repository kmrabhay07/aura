"""One cancellable pipeline for the existing Jarvis window and both input modes."""
import threading

from .actions import Approval
from .agent import AuraAgent
from .conversation import Cancelled, Conversation, Sentences, normalize_request
from .voice import Recorder, Speaker, Transcriber
from .history import HistoryStore
from .browser_agent import BrowserAgent


def provider_error_hint(error):
    # Display only fixed messages. Provider payloads can contain private inputs.
    status = getattr(error, "status_code", None)
    code = getattr(error, "code", None)
    if status in (401, 403):
        return "AI access was denied. Check the selected provider, API key and project permissions in Settings."
    if status == 429:
        return "The AI provider reported a rate or quota limit. Check project usage and billing, then retry."
    if status == 404 or code == "model_not_found":
        return "The AI model is unavailable to this key. Check Provider and Model ID in Settings."
    if status in (400, 422):
        param = getattr(error, "param", None)
        if isinstance(param, str) and param.startswith(("tools", "tool_choice")):
            return "The AI provider rejected the action tools. Check that the selected model supports function calling."
        if param == "model":
            return "The AI provider rejected the model selection. Check Provider and Model ID in Settings."
        return "The AI provider rejected this request. Check that the selected model supports chat and function calling. For OpenAI (GPT), try gpt-4.1-mini."
    return None


class Pipeline:
    def __init__(self, notify, agent_factory=AuraAgent, recorder=None,
                 transcriber=None, speaker=None):
        self.notify = notify
        self.conversation = Conversation()
        self.recorder = recorder or Recorder()
        self.transcriber = transcriber or Transcriber()
        self.speaker = speaker or Speaker(self.emit)
        self.agent_factory = agent_factory
        self._agent = None
        self._config_epoch = 0
        self._agent_lock = threading.Lock()
        self._closed = False
        self._threads = set()
        self._threads_lock = threading.Lock()
        self.history_store = None
        self.session_id = HistoryStore.new_id()
        self.browser = BrowserAgent()

    def emit(self, turn, state, detail=""):
        if not self._closed and self.conversation.active(turn):
            self.notify(turn, state, detail)

    def cancel(self):
        self.conversation.cancel()

    def reset(self):
        self.conversation.clear()
        with self._agent_lock:
            self._config_epoch += 1
            self._agent = None

    def close(self):
        self._closed = True
        self.cancel()
        self.speaker.close()
        self.browser.close()

    def new_session(self, messages=(), session_id=None):
        self.cancel()
        self.conversation.restore(messages)
        self.session_id = session_id or HistoryStore.new_id()

    def begin(self, prompt=None, spoken=False, screen=None, allow_browser=False):
        if self._closed:
            return None
        turn = self.conversation.begin()
        with self._threads_lock:
            self._threads = {t for t in self._threads if t.is_alive()}
            # A cancelled network/native call can still be unwinding. Bound
            # concurrent work instead of spawning unlimited blocked workers.
            if len(self._threads) >= 3:
                self.emit(turn, "error", "Previous work is stopping; please try again shortly")
                return turn
            thread = threading.Thread(target=self._run, args=(turn, prompt, spoken, screen, allow_browser, self.session_id),
                                      daemon=True, name=f"Jarvis turn {turn.number}")
            self._threads.add(thread)
            thread.start()
        return turn

    def release(self):
        turn = self.conversation.current
        if turn:
            turn.released.set()

    def _run(self, turn, prompt, spoken, screen, allow_browser, session_id):
        try:
            # Prior turn cancellation is set before this wait; never open a
            # microphone while the prior response is still playing.
            if prompt is None and not self.speaker.wait_quiet():
                raise RuntimeError("Speech is still stopping; try again")
            turn.check()
            if prompt is None:
                self.emit(turn, "starting", "Opening microphone…")
                audio, capped = self.recorder.capture(
                    turn, lambda: self.emit(turn, "listening", "Release to send · Esc to cancel"))
                turn.check()
                self.emit(turn, "transcribing", "First use may download the local speech model")
                if capped:
                    self.emit(turn, "notice", "Recording stopped at the 120-second safety limit")
                prompt = self.transcriber.transcribe(audio, turn)
            prompt = normalize_request(prompt)
            if not prompt:
                self.emit(turn, "idle", "No speech detected")
                return
            self.emit(turn, "heard", prompt)
            self.emit(turn, "thinking", "Jarvis is thinking…")
            turn.check()
            with self._agent_lock:
                agent = self._agent
                epoch = self._config_epoch
            if agent is None:
                # Imports/client construction never hold a lock needed by UI reset.
                agent = self.agent_factory()
                turn.check()
                with self._agent_lock:
                    if epoch != self._config_epoch:
                        raise Cancelled()
                    self._agent = agent
            sentences = Sentences()
            actions = []

            def text(chunk):
                turn.check()
                self.emit(turn, "text", chunk)
                if spoken:
                    for sentence in sentences.feed(chunk):
                        self.speaker.say(turn, sentence)

            def progress(message):
                actions.append(message)
                self.emit(turn, "action", message)

            def approve(name, arguments):
                request = Approval(turn, name, arguments)
                self.emit(turn, "approval", request)
                allowed = request.wait()
                self.emit(turn, "approval_done", request)
                self.emit(turn, "thinking", "Jarvis is thinking…")
                return allowed

            extras = {}
            if screen is not None:
                extras.update(screen=screen,on_annotations=lambda shapes:self.emit(turn,"annotations",(screen,shapes)))
            if allow_browser:
                extras['browser']=self.browser
            result = agent.run(prompt, progress, history=self.conversation.history(),
                               turn=turn, on_text=text, approve=approve, **extras)
            turn.check()
            memory_reply = result + ("\nAction results: " + "\n".join(actions) if actions else "")
            completed = self.conversation.commit_snapshot(turn,prompt,memory_reply)
            if completed is None:
                return
            store = self.history_store
            if store:
                try:
                    store.save(session_id,completed)
                except Exception:
                    self.emit(turn,"notice","Could not save history; the reply is still available in this session")
            self.emit(turn, "answer_done", result)
            if spoken:
                for sentence in sentences.feed("", final=True):
                    self.speaker.say(turn, sentence)
                self.speaker.finish(turn)
            else:
                self.emit(turn, "idle", "Ready")
        except Cancelled:
            pass
        except Exception as exc:
            # Provider exception strings can contain URLs, headers or keys.
            # Keep errors actionable without rendering raw exception payloads.
            if isinstance(exc, RuntimeError) and str(exc) in {
                    "Add your API key in Settings first", "Speech is still stopping; try again",
                    "Microphone overflow or device error; try again"}:
                detail = str(exc)
            else:
                detail = provider_error_hint(exc) or (
                    f"{type(exc).__name__}: request failed. Check microphone, model availability, provider settings or connection."
                )
            self.emit(turn, "error", detail)
            turn.cancel.set()
