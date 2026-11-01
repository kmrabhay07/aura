import threading

from aura.pipeline import Pipeline


class SilentSpeaker:
    def __init__(self):
        self.finished = []
    def wait_quiet(self, timeout=2):
        return True
    def say(self, turn, text):
        self.finished.append(text)
    def finish(self, turn):
        pass
    def close(self):
        pass


def wait_workers(pipeline):
    for worker in list(pipeline._threads):
        worker.join(3)
        assert not worker.is_alive()


def test_pipeline_reuses_agent_has_context_and_normalizes_spoken_name():
    events = []
    creations = []
    requests = []
    class Agent:
        def __init__(self):
            creations.append(True)
        def run(self, prompt, progress, **kwargs):
            requests.append((prompt, kwargs["history"]))
            kwargs["on_text"]("Hello there.")
            return "Hello there."
    speaker = SilentSpeaker()
    pipe = Pipeline(lambda *e: events.append(e), agent_factory=Agent, speaker=speaker)
    try:
        pipe.begin("Jarvis, remember this", spoken=True)
        wait_workers(pipe)
        pipe.begin("What did I say?")
        wait_workers(pipe)
        assert len(creations) == 1
        assert requests[0] == ("remember this", [])
        assert requests[1][1][0]["content"] == "remember this"
        assert speaker.finished == ["Hello there."]
        assert any(e[1] == "thinking" for e in events)
    finally:
        pipe.close()


def test_cancelled_request_cannot_publish_commit_or_open_approval():
    entered = threading.Event()
    unblock = threading.Event()
    events = []
    class Agent:
        def run(self, prompt, progress, **kwargs):
            if prompt == "old":
                entered.set()
                assert unblock.wait(3)
                kwargs["on_text"]("stale")
            kwargs["on_text"]("new answer")
            return "new answer"
    pipe = Pipeline(lambda *e: events.append(e), agent_factory=Agent, speaker=SilentSpeaker())
    try:
        old = pipe.begin("old")
        assert entered.wait(2)
        pipe.begin("new")
        unblock.set()
        wait_workers(pipe)
        assert not any(e[0] is old and e[1] == "text" for e in events)
        assert [m["content"] for m in pipe.conversation.history()] == ["new", "new answer"]
    finally:
        pipe.close()


def test_release_reaches_capture_even_before_worker_starts():
    entered = threading.Event()
    unblock = threading.Event()
    observed = []
    class Speaker(SilentSpeaker):
        def wait_quiet(self, timeout=2):
            entered.set()
            return unblock.wait(2)
    class Recorder:
        def capture(self, turn, listening):
            observed.append(turn.released.is_set())
            return [], False
    class Transcriber:
        def transcribe(self, audio, turn):
            return ""
    pipe = Pipeline(lambda *e: None, recorder=Recorder(), transcriber=Transcriber(), speaker=Speaker())
    try:
        pipe.begin()
        assert entered.wait(2)
        pipe.release()
        unblock.set()
        wait_workers(pipe)
        assert observed == [True]
    finally:
        pipe.close()


def test_cancel_while_awaiting_approval_unblocks_and_never_commits():
    waiting = threading.Event()
    class Agent:
        def run(self, prompt, progress, **kwargs):
            kwargs["approve"]("open_app", {"app": "notepad"})
            return "should not commit"
    def notify(turn, state, detail):
        if state == "approval":
            waiting.set()
    pipe = Pipeline(notify, agent_factory=Agent, speaker=SilentSpeaker())
    try:
        pipe.begin("open")
        assert waiting.wait(2)
        pipe.cancel()
        wait_workers(pipe)
        assert pipe.conversation.history() == []
    finally:
        pipe.close()


def test_provider_errors_do_not_expose_raw_secret_payloads():
    events = []
    class Agent:
        def run(self, *args, **kwargs):
            raise ValueError("Authorization: Bearer SECRET")
    pipe = Pipeline(lambda *e: events.append(e), agent_factory=Agent, speaker=SilentSpeaker())
    try:
        pipe.begin("hello")
        wait_workers(pipe)
        errors = [e[2] for e in events if e[1] == "error"]
        assert errors and "SECRET" not in errors[0]
        assert pipe.conversation.history() == []
    finally:
        pipe.close()


def test_pipeline_will_not_capture_while_speech_has_not_stopped():
    events = []
    class BusySpeaker(SilentSpeaker):
        def wait_quiet(self, timeout=2):
            return False
    class ForbiddenRecorder:
        def capture(self, *args):
            raise AssertionError("Microphone opened while speech was playing")
    pipe = Pipeline(lambda *e: events.append(e), recorder=ForbiddenRecorder(), speaker=BusySpeaker())
    try:
        pipe.begin()
        wait_workers(pipe)
        assert any(e[1] == "error" and "Speech is still stopping" in e[2] for e in events)
    finally:
        pipe.close()


def test_close_returns_while_provider_unwinds_and_suppresses_late_results():
    entered = threading.Event()
    release = threading.Event()
    events = []
    class Agent:
        def run(self, prompt, progress, **kwargs):
            entered.set()
            assert release.wait(2)
            kwargs["on_text"]("late")
            return "late"
    pipe = Pipeline(lambda *e: events.append(e), agent_factory=Agent, speaker=SilentSpeaker())
    pipe.begin("hello")
    assert entered.wait(2)
    pipe.close()
    count = len(events)
    release.set()
    wait_workers(pipe)
    assert len(events) == count
    assert not pipe.conversation.history()


def test_settings_reset_does_not_wait_for_client_construction():
    entered = threading.Event()
    release = threading.Event()
    def factory():
        entered.set()
        assert release.wait(2)
        return object()
    pipe = Pipeline(lambda *e: None, agent_factory=factory, speaker=SilentSpeaker())
    try:
        pipe.begin("hello")
        assert entered.wait(2)
        pipe.reset()
        release.set()
        wait_workers(pipe)
        assert pipe._agent is None
    finally:
        release.set()
        pipe.close()


def test_opt_in_history_saves_text_only_and_new_session_has_a_new_id(tmp_path):
    from aura.history import HistoryStore
    from aura.screen import ScreenFrame
    class Agent:
        def run(self,prompt,progress,**kwargs):
            assert kwargs['screen'].jpeg==b'PRIVATE_IMAGE_NOT_TO_SAVE'
            kwargs['on_text']('Answer from the screen.')
            return 'Answer from the screen.'
    store=HistoryStore(tmp_path/'history.sqlite3')
    pipe=Pipeline(lambda *e:None,agent_factory=Agent,speaker=SilentSpeaker())
    try:
        pipe.history_store=store
        key=pipe.session_id
        pipe.begin('question',screen=ScreenFrame(b'PRIVATE_IMAGE_NOT_TO_SAVE','test',(0,0,100,100),(100,100)))
        wait_workers(pipe)
        messages=store.load(key)
        assert messages[0]['content']=='question'
        assert 'PRIVATE_IMAGE' not in str(messages)
        pipe.new_session()
        assert pipe.session_id!=key and pipe.conversation.history()==[]
    finally:
        pipe.close()
