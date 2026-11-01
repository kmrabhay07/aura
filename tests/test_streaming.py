"""Fake streaming transports test provider history and tool approval protocols."""
from types import SimpleNamespace as NS
import pytest

from aura.agent import AuraAgent
from aura.claude import run_claude
from aura.conversation import Cancelled, Turn


class Stream:
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False
    def __iter__(self):
        yield from self.chunks
    def close(self):
        self.closed = True


def chunk(text=None, calls=None):
    return NS(choices=[NS(delta=NS(content=text, tool_calls=calls))])


def agent_with_streams(streams):
    requests = []
    def create(**kwargs):
        # Snapshot before the adapter appends more messages.
        requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return streams.pop(0)
    agent = AuraAgent.__new__(AuraAgent)
    agent.provider = "Grok (xAI)"
    agent.model = "fake"
    agent.client = NS(chat=NS(completions=NS(create=create)))
    return agent, requests


def test_openai_streaming_context_and_approved_fragmented_tool_call(monkeypatch):
    executed = []
    monkeypatch.setattr("aura.agent.execute", lambda *args: executed.append(args) or "Launched notepad")
    tool1 = NS(index=0, id="call1", function=NS(name="open_", arguments='{"app":'))
    tool2 = NS(index=0, id=None, function=NS(name="app", arguments='"notepad"}'))
    first = Stream([chunk(calls=[tool1]), chunk(calls=[tool2])])
    second = Stream([chunk("Opened "), chunk("Notepad.")])
    agent, requests = agent_with_streams([first, second])
    text = []
    history = [{"role": "user", "content": "Remember my editor"},
               {"role": "assistant", "content": "Notepad"}]
    assert agent.run("Open it", history=history, on_text=text.append,
                     approve=lambda name, args: name == "open_app" and args == {"app": "notepad"}) == "Opened Notepad."
    assert text == ["Opened ", "Notepad."]
    assert requests[0]["messages"][1:3] == history
    assert requests[1]["messages"][-1] == {
        "role": "tool", "tool_call_id": "call1", "content": "Launched notepad"}
    assert executed == [("open_app", {"app": "notepad"})]
    assert first.closed and second.closed


def test_cancelled_stream_closes_and_never_requests_tool_execution(monkeypatch):
    turn = Turn(1)
    def chunks():
        yield chunk("Hello")
        turn.cancel.set()
        yield chunk(calls=[NS(index=0, id="1", function=NS(name="open_app", arguments='{"app":"notepad"}'))])
    stream = Stream(chunks())
    agent, _ = agent_with_streams([stream])
    monkeypatch.setattr("aura.agent.execute", lambda *a: pytest.fail("Cancelled action executed"))
    with pytest.raises(Cancelled):
        agent.run("hi", turn=turn, approve=lambda *a: True)
    assert stream.closed


def test_anthropic_receives_history_and_same_denial_boundary(monkeypatch):
    calls = []
    monkeypatch.setattr("aura.agent.execute", lambda *a: pytest.fail("Denied action executed"))
    class Context:
        def __init__(self, text, blocks):
            self.text_stream = iter(text)
            self.blocks = blocks
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get_final_message(self):
            return NS(content=self.blocks)
    streams = [Context([], [NS(type="tool_use", id="tool1", name="open_app", input={"app": "notepad"})]),
               Context(["I did not open it."], [NS(type="text", text="I did not open it.")])]
    def stream(**kwargs):
        calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return streams.pop(0)
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    text = []
    assert run_claude(NS(messages=NS(stream=stream)), "fake", "open", lambda x: None,
                      history=history, on_text=text.append, approve=lambda *a: False) == "I did not open it."
    assert calls[0]["messages"][:2] == history
    assert "denied" in calls[1]["messages"][-1]["content"][0]["content"]
    assert text == ["I did not open it."]


def test_screen_images_are_added_only_to_this_turn_and_guidance_is_routed(monkeypatch):
    import json
    from aura.screen import ScreenFrame
    values={'shapes':[{'kind':'circle','x':.1,'y':.1,'x2':.2,'y2':.2,'label':'Look here'}]}
    tool=NS(index=0,id='draw1',function=NS(name='annotate_screen',arguments=json.dumps(values)))
    agent,requests=agent_with_streams([Stream([chunk(calls=[tool])]),Stream([chunk('Here it is.')])])
    annotations=[]
    monkeypatch.setattr('aura.agent.execute',lambda *a:pytest.fail('Guidance executed input'))
    screen=ScreenFrame(b'synthetic-image','display',(0,0,1920,1080),(1600,900))
    result=agent.run('where?',screen=screen,on_annotations=annotations.append)
    assert result=='Here it is.'
    assert annotations==[values['shapes']]
    assert requests[0]['messages'][-1]['content'][1]['type']=='image_url'
    assert any(t['function']['name']=='annotate_screen' for t in requests[0]['tools'])
