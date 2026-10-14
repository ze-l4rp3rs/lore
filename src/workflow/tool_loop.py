import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.providers.base import Message, Provider, ToolCall
from src.tools import AVAILABLE_FUNCTIONS, TOOL_SCHEMAS, call_tool

_THINK_BLOCK = re.compile(r"<(think|thinking)>.*?</\1>", re.IGNORECASE | re.DOTALL)
_THINK_END = re.compile(r"</(?:think|thinking)>", re.IGNORECASE)
_THINK_OPEN = re.compile(r"<(?:think|thinking)>", re.IGNORECASE)


def split_reasoning(
    text: str
) -> tuple[str, str]:
    # reasoning models sometimes write their thinking into the answer: as <think> blocks, ended by a
    # stray </think> whose opening tag was lost, or opened and never closed (cut off); keep only the answer
    reasoning = [match.group(0) for match in _THINK_BLOCK.finditer(text)]
    text = _THINK_BLOCK.sub("", text)
    ends = list(_THINK_END.finditer(text))
    if ends:
        reasoning.append(text[:ends[-1].start()])
        text = text[ends[-1].end():]
    opened = _THINK_OPEN.search(text)
    if opened:
        reasoning.append(text[opened.start():])
        text = text[:opened.start()]
    return text.strip(), "\n\n".join(part.strip() for part in reasoning if part.strip())


def run_tool(
    call: ToolCall,
    user: Any
) -> str:
    try:
        arguments = json.loads(call.arguments or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")
        if call.name not in AVAILABLE_FUNCTIONS:
            raise KeyError(f"unknown tool {call.name!r}")
        return str(call_tool(call.name, arguments, user))
    except Exception as caught:
        # never let a bad or unknown tool call kill the run; tell the model instead
        return f"Tool error ({call.name}): {type(caught).__name__}: {caught}"


def ask(
    provider: Provider,
    model: str,
    messages: list[Message],
    user: Any = None
) -> str:
    # every turn is appended to messages, tool turns included, so the caller can continue the conversation
    tools = TOOL_SCHEMAS or None

    for step in range(config.MAX_TOOL_STEPS + 1):
        # out of tool budget: the last call must answer from the results it already has
        tool_choice = "auto" if step < config.MAX_TOOL_STEPS else "none"
        completion = provider.complete(model, messages, tools, tool_choice)
        text, leaked = split_reasoning(completion.text)
        reasoning = [part for part in (completion.reasoning.strip(), leaked) if part]
        if reasoning:
            # kept out of the answer, but not lost: stderr, so stdout carries only the answer
            print("[model reasoning]\n" + "\n\n".join(reasoning), file=sys.stderr)

        if not completion.tool_calls:
            if text == "":
                raise RuntimeError(f"Empty response from {model} (finish_reason = {completion.finish_reason}).")
            messages.append({"role": "assistant", "content": text})
            return text
        if tools is None or tool_choice == "none":
            raise RuntimeError(f"{model} called a tool when tools were not allowed.")

        # text written next to a tool call is dropped: the model must write the WHOLE
        # answer after the results arrive, otherwise only the tail is ever returned
        messages.append({"role": "assistant", "content": "", "tool_calls": completion.tool_calls})
        for call in completion.tool_calls:
            messages.append({"role": "tool", "content": run_tool(call, user), "tool_call_id": call.id})

    raise AssertionError("unreachable: the last step never allows tools")
