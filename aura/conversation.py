"""Session-only conversation state and cancellation, independent of Qt."""
from dataclasses import dataclass, field
import re
import threading


class Cancelled(Exception):
    pass


@dataclass
class Turn:
    number: int
    cancel: threading.Event = field(default_factory=threading.Event)
    released: threading.Event = field(default_factory=threading.Event)

    def check(self):
        if self.cancel.is_set():
            raise Cancelled()


def normalize_request(text):
    """Jarvis is an optional address after activation, never a wake word."""
    return re.sub(r"^\s*jarvis(?=$|[\s,:;.!?—-])[\s,:;.!?—-]*", "", text, count=1, flags=re.I).strip()


class Conversation:
    def __init__(self, max_turns=12, max_chars=24000):
        self.max_turns = max_turns
        self.max_chars = max_chars
        self._pairs = []
        self._lock = threading.RLock()
        self._number = 0
        self.current = None

    def begin(self):
        with self._lock:
            self.cancel()
            self._number += 1
            self.current = Turn(self._number)
            return self.current

    def cancel(self):
        with self._lock:
            if self.current:
                self.current.cancel.set()
                self.current.released.set()
                self.current = None

    def active(self, turn):
        with self._lock:
            return self.current is turn and not turn.cancel.is_set()

    def history(self):
        with self._lock:
            return [dict(message) for pair in self._pairs for message in pair]

    def commit(self, turn, prompt, reply):
        with self._lock:
            if not self.active(turn):
                return False
            # Complete pairs only; tool protocols remain inside their own turn.
            self._pairs.append([
                {"role": "user", "content": prompt[:8000]},
                {"role": "assistant", "content": reply[:8000]},
            ])
            while self._pairs and (len(self._pairs) > self.max_turns or
                    sum(len(m["content"]) for p in self._pairs for m in p) > self.max_chars):
                self._pairs.pop(0)
            return True

    def commit_snapshot(self, turn, prompt, reply):
        with self._lock:
            return self.history() if self.commit(turn,prompt,reply) else None

    def clear(self):
        with self._lock:
            self.cancel()
            self._pairs.clear()

    def restore(self, messages):
        if len(messages)%2 or any(m.get('role') != ('user' if i%2==0 else 'assistant') or
                not isinstance(m.get('content'),str) for i,m in enumerate(messages)):
            raise ValueError('Conversation must contain complete plain-text pairs')
        with self._lock:
            self.clear()
            self._pairs = [[{'role':m['role'],'content':m['content'][:8000]} for m in messages[i:i+2]]
                           for i in range(0,len(messages),2)][-self.max_turns:]
            while self._pairs and sum(len(m['content']) for p in self._pairs for m in p)>self.max_chars:
                self._pairs.pop(0)


class Sentences:
    def __init__(self):
        self.pending = ""

    def feed(self, text, final=False):
        self.pending += text
        output = []
        while self.pending:
            match = re.search(r"[.!?](?:\s|$)|\n", self.pending)
            end = match.end() if match else 0
            if not end and len(self.pending) > 240:
                end = self.pending.rfind(" ", 0, 240) + 1 or 240
            if not end:
                if final:
                    end = len(self.pending)
                else:
                    break
            phrase, self.pending = self.pending[:end].strip(), self.pending[end:]
            if phrase:
                output.append(phrase)
        return output
