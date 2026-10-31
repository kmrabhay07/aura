"""Constrained tool-calling agent for initial Windows/browser tasks."""
import json
import os
import subprocess
import sys
import webbrowser
from urllib.parse import quote_plus, urlparse
from .browser import browse
from .providers import make_client, PROVIDERS
from .settings import Settings
from .system_tools import system_action

from openai import OpenAI

SYSTEM = """You are AURA, a Windows assistant. Use available tools when needed.
Never claim an action succeeded unless the tool returned success. Ask for confirmation
before any destructive, financial, or external communication action. Do not invent tools."""

TOOLS = [
    {"type": "function", "function": {"name": "open_url", "description": "Open a web URL in the default browser", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "web_search", "description": "Search using the default browser", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "system_control", "description": "Control Windows system volume, media play/pause, next/previous track, or lock screen. Lock screen requires user confirmation before execution.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["volume_up", "volume_down", "volume_mute", "play_pause", "next_track", "previous_track", "lock_screen"]}}, "required": ["action"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "browser", "description": "Open web pages, search Google, or open Apple Music in an automated Chromium session", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["search", "navigate", "music"]}, "value": {"type": "string"}}, "required": ["action"], "additionalProperties": False}}},
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
        self.client = make_client(self.provider, key)

    def run(self, command, progress=lambda message: None):
        if self.provider == "Claude (Anthropic)":
            from .claude import run_claude
            return run_claude(self.client, self.model, command, progress)
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": command}]
        for _ in range(6):
            response = self.client.chat.completions.create(model=self.model, messages=messages, tools=TOOLS, tool_choice="auto")
            msg = response.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                return msg.content or "Completed."
            for call in msg.tool_calls:
                try:
                    result = execute(call.function.name, json.loads(call.function.arguments))
                except (KeyError, ValueError, OSError) as exc:
                    result = f"Action failed: {exc}"
                progress(f"{call.function.name}: {result}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        return "Stopped after the maximum number of action rounds."
