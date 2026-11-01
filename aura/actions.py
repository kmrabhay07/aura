"""Validated, cancellable approval requests shared by both provider adapters."""
from dataclasses import dataclass, field
import threading


@dataclass
class Approval:
    turn: object
    name: str
    arguments: dict
    resolved: threading.Event = field(default_factory=threading.Event)
    allowed: bool = False

    def answer(self, allowed):
        # UI resolves a request once; cancellation invalidates any later answer.
        if not self.resolved.is_set():
            self.allowed = bool(allowed) and not self.turn.cancel.is_set()
            self.resolved.set()

    def wait(self, timeout=60):
        import time
        deadline = time.monotonic() + timeout
        while not self.resolved.wait(0.05):
            self.turn.check()
            if time.monotonic() >= deadline:
                self.answer(False)
                return False
        self.turn.check()
        return self.allowed


def validate_action(name, args):
    from .agent import TOOLS
    from .browser_agent import BROWSER_TOOL
    schema = next((t["function"]["parameters"] for t in [*TOOLS,BROWSER_TOOL]
                   if t["function"]["name"] == name), None)
    if schema is None or not isinstance(args, dict):
        raise ValueError("Unsupported action")
    props = schema["properties"]
    if set(args) - set(props) or any(key not in args for key in schema.get("required", [])):
        raise ValueError("Invalid action fields")
    for key, value in args.items():
        if not isinstance(value, str) or len(value) > 4000:
            raise ValueError("Invalid action value")
        if "enum" in props[key] and value not in props[key]["enum"]:
            raise ValueError("Unsupported action value")
    return args


def approved_execute(name, args, turn, approve, executor=None):
    from .agent import execute
    validate_action(name, args)
    turn.check()
    if approve is None or not approve(name, dict(args)):
        return "Action denied or approval expired; nothing executed"
    turn.check()
    return (executor or execute)(name, args)
