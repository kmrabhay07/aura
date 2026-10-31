"""Anthropic tool use adapter with the same constrained local actions."""
import json
from .agent import execute, SYSTEM, TOOLS

def run_claude(client, model, prompt, progress):
    tools = [
        {"name": t["function"]["name"], "description": t["function"]["description"],
         "input_schema": t["function"]["parameters"]}
        for t in TOOLS
    ]
    messages = [{"role": "user", "content": prompt}]
    for _ in range(6):
        response = client.messages.create(model=model, max_tokens=1200, system=SYSTEM, messages=messages, tools=tools)
        messages.append({"role": "assistant", "content": response.content})
        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            return "\n".join(block.text for block in response.content if block.type == "text") or "Completed."
        results = []
        for call in calls:
            try:
                outcome = execute(call.name, call.input)
            except (KeyError, ValueError, OSError) as exc:
                outcome = f"Action failed: {exc}"
            progress(f"{call.name}: {outcome}")
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": outcome})
        messages.append({"role": "user", "content": results})
    return "Stopped after the maximum number of action rounds."
