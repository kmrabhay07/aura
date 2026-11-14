"""Anthropic streaming adapter using the same session and approval boundary."""
from .agent import SYSTEM, TOOLS
from .agent_tools import route_tool, tools_for, system_for
from .conversation import Turn


def run_claude(client, model, prompt, progress, *, history=(), turn=None,
               on_text=lambda text: None, approve=None, screen=None,
               on_annotations=lambda shapes:None, browser=None):
    turn = turn or Turn(0)
    tools = [{"name": t["function"]["name"], "description": t["function"]["description"],
              "input_schema": t["function"]["parameters"]} for t in tools_for(TOOLS,screen,browser)]
    messages = [*history, {"role": "user", "content": screen.content(prompt,anthropic=True) if screen else prompt}]
    answer = []
    for _ in range(6):
        turn.check()
        with client.messages.stream(model=model, max_tokens=1200, system=system_for(SYSTEM,screen,browser),
                                    messages=messages, tools=tools) as stream:
            for text in stream.text_stream:
                turn.check()
                answer.append(text)
                on_text(text)
            response = stream.get_final_message()
        turn.check()
        messages.append({"role": "assistant", "content": response.content})
        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            if not answer:
                on_text("Completed.")
            return "".join(answer) or "Completed."
        results = []
        for call in calls:
            try:
                outcome = route_tool(call.name,call.input,turn,approve,
                                     screen=screen,on_annotations=on_annotations,browser=browser)
            except (KeyError, ValueError, OSError):
                outcome = "Action failed: invalid arguments or local action error"
            turn.check()
            progress(f"{call.name}: {outcome}")
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": outcome})
        messages.append({"role": "user", "content": results})
    final = "Stopped after the maximum number of action rounds."
    on_text(final)
    return "".join(answer) + final
