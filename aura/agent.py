"""Constrained tool-calling agent for initial Windows/browser tasks."""
import json
import subprocess
import sys
import webbrowser
from urllib.parse import quote_plus, urlparse
from .browser import browse
from .providers import make_client
from .settings import Settings
from .system_tools import system_action

SYSTEM = """You are Jarvis, a Windows assistant. You see only screenshots explicitly shared for the current request.
A leading Jarvis is optional after push-to-talk. Never suggest you are always listening. Use available tools when needed.
Never claim an action succeeded unless the tool returned success. Ask for confirmation
before any destructive, financial, or external communication action. Do not invent tools."""

TOOLS = [
    {"type": "function", "function": {"name": "open_url", "description": "Open a web URL in the default browser", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "web_search", "description": "Search using the default browser", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "system_control", "description": "Control Windows system volume, media play/pause, next/previous track, or lock screen. Lock screen requires user confirmation before execution.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["volume_up", "volume_down", "volume_mute", "play_pause", "next_track", "previous_track", "lock_screen"]}}, "required": ["action"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "browser", "description": "Open web pages, search Google, or open Apple Music in the default browser", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["search", "navigate", "music", "music_search", "chatgpt"]}, "value": {"type": "string"}}, "required": ["action"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "open_app", "description": "Open an allowed Windows application", "parameters": {"type": "object", "properties": {"app": {"type": "string", "enum": ["notepad", "calculator", "explorer"]}}, "required": ["app"], "additionalProperties": False}}},
]

def execute(name, args):
    if name == "web_search":
        return "Search opened in browser" if webbrowser.open("https://www.google.com/search?q=" + quote_plus(args["query"])) else "Browser could not be opened"
    if name == "open_url":
        url = args["url"]
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.username or parsed.password:
            return "Blocked: invalid URL"
        return "URL opened in browser" if webbrowser.open(url) else "Browser could not be opened"
    if name == "open_app":
        if sys.platform != "win32":
            return "Windows applications require Windows"
        apps = {"notepad": "notepad.exe", "calculator": "calc.exe", "explorer": "explorer.exe"}
        if args["app"] not in apps:
            return "Unsupported application"
        subprocess.Popen([apps[args["app"]]])
        return f"Launched {args['app']}"
    if name == "system_control":
        return system_action(args["action"])
    if name == "browser":
        return browse(args["action"], args.get("value"))
    return "Unsupported action"

class AuraAgent:
    def __init__(self):
        settings = Settings()
        self.provider = settings.provider()
        self.model = settings.model()
        key = settings.api_key(self.provider)
        if not key and self.provider != "Ollama (local)":
            raise RuntimeError("Add your API key in Settings first")
        # Bounded network waits; do not retry a cancelled interaction invisibly.
        self.client = make_client(self.provider, key).with_options(timeout=20, max_retries=0)

    def run(self, command, progress=lambda message: None, *, history=(),
            turn=None, on_text=lambda text: None, approve=None,
            screen=None, on_annotations=lambda shapes:None, browser=None):
        from .conversation import Turn
        from .agent_tools import route_tool, tools_for, system_for
        turn = turn or Turn(0)
        turn.check()
        if self.provider == "Claude (Anthropic)":
            from .claude import run_claude
            return run_claude(self.client, self.model, command, progress,
                              history=history, turn=turn, on_text=on_text, approve=approve,
                              screen=screen,on_annotations=on_annotations,browser=browser)
        messages = [{"role": "system", "content": system_for(SYSTEM,screen,browser)}, *history,
                    {"role": "user", "content": screen.content(command) if screen else command}]
        tools=tools_for(TOOLS,screen,browser)
        answer = []
        for round_index in range(6):
            turn.check()
            calls = {}
            text = []
            chat = self.client.chat.completions
            actions_available = True
            try:
                stream = chat.create(model=self.model, messages=messages, tools=tools, stream=True)
            except Exception as error:
                # Retry only before any output or actions. Keep explicit browser
                # tasks intact so they cannot silently turn into plain chat.
                if (round_index != 0 or browser is not None
                        or getattr(error, "status_code", None) not in (400, 422)
                        or getattr(error, "param", None) == "model"):
                    raise
                turn.check()
                messages[0]["content"] += (
                    "\nAction and annotation tools are unavailable for this reply. "
                    "Answer conversationally and do not claim to perform actions."
                )
                stream = chat.create(model=self.model, messages=messages, stream=True)
                actions_available = False
            try:
                for chunk in stream:
                    turn.check()
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        text.append(delta.content)
                        answer.append(delta.content)
                        on_text(delta.content)
                    for item in (delta.tool_calls or []) if actions_available else ():
                        call = calls.setdefault(item.index, {"id": "", "type": "function",
                            "function": {"name": "", "arguments": ""}})
                        if item.id:
                            call["id"] = item.id
                        if item.function:
                            call["function"]["name"] += item.function.name or ""
                            call["function"]["arguments"] += item.function.arguments or ""
            finally:
                stream.close()
            turn.check()
            if not actions_available:
                progress("The provider accepted chat without action tools. No action was performed.")
            if not calls:
                if not answer:
                    on_text("Completed.")
                return "".join(answer) or "Completed."
            messages.append({"role": "assistant", "content": "".join(text) or None,
                             "tool_calls": [calls[i] for i in sorted(calls)]})
            for index in sorted(calls):
                call = calls[index]
                try:
                    args = json.loads(call["function"]["arguments"])
                    result = route_tool(call["function"]["name"],args,turn,approve,
                                        screen=screen,on_annotations=on_annotations,browser=browser)
                except (KeyError, ValueError, OSError):
                    result = "Action failed: invalid arguments or local action error"
                turn.check()
                progress(f"{call['function']['name']}: {result}")
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        final = "Stopped after the maximum number of action rounds."
        on_text(final)
        return "".join(answer) + final
