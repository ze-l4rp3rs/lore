import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv

import config
from src.tools import AVAILABLE_FUNCTIONS, TOOL_SCHEMAS, call_tool

_client = None


def client():
    # created on first use, so this module imports without the SDK
    global _client
    if _client is None:
        from groq import Groq
        load_dotenv()
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


def run_tool(
    call: Any,
    user: Any
) -> str:
    name = call.function.name
    try:
        arguments = json.loads(call.function.arguments or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")
        if name not in AVAILABLE_FUNCTIONS:
            raise KeyError(f"unknown tool {name!r}")
        return str(call_tool(name, arguments, user))
    except Exception as caught:
        # never let a bad or unknown tool call kill the run; tell the model instead
        return f"Tool error ({name}): {type(caught).__name__}: {caught}"


def ask(
    model: str,
    messages: list[dict],
    user: Any = None
) -> str:
    # every turn is appended to messages, tool turns included, so the caller can continue the conversation
    tools = TOOL_SCHEMAS or None

    for step in range(config.MAX_TOOL_STEPS + 1):
        # out of tool budget: the last call must answer from the results it already has
        tool_choice = "auto" if step < config.MAX_TOOL_STEPS else "none"
        extra: dict[str, Any] = {"tools": tools, "tool_choice": tool_choice} if tools else {}
        response = client().chat.completions.create(
            model=model,
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
            messages=messages,
            **extra,
        )
        choice = response.choices[0]
        text = (choice.message.content or "").strip()

        if not choice.message.tool_calls:
            if text == "":
                raise RuntimeError(f"Empty response from {model} (finish_reason = {choice.finish_reason}).")
            messages.append({"role": "assistant", "content": text})
            return text
        if tools is None or tool_choice == "none":
            raise RuntimeError(f"{model} called a tool when tools were not allowed.")

        # text written next to a tool call is dropped: the model must write the WHOLE
        # answer after the results arrive, otherwise only the tail is ever returned
        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in choice.message.tool_calls
            ],
        })
        for call in choice.message.tool_calls:
            messages.append({"role": "tool", "content": run_tool(call, user), "tool_call_id": call.id})

    raise AssertionError("unreachable: the last step never allows tools")
