import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.providers.base import Completion, Message, ToolCall

_client = None


def client():
    # created on first use, so this module imports (and its translation is testable) without the SDK
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic(api_key=os.getenv(config.PROVIDER_KEYS["claude"]))
    return _client


def to_anthropic_tools(
    tools: list[dict]
) -> list[dict[str, Any]]:
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


def to_anthropic_messages(
    messages: list[Message]
) -> tuple[str, list[dict[str, Any]]]:
    # Anthropic takes the system prompt separately; everything else is a plain text turn
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    chat = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    return system, chat


def complete(
    model: str,
    messages: list[Message],
    tools: list[dict] | None = None,
    tool_choice: str = "auto"
) -> Completion:
    system, chat = to_anthropic_messages(messages)
    extra: dict[str, Any] = {}
    if system:
        extra["system"] = system
    if tools:
        extra["tools"] = to_anthropic_tools(tools)

    response = client().messages.create(
        model=model,
        max_tokens=config.MAX_TOKENS,
        messages=chat,
        **extra,
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    calls = [
        ToolCall(id=block.id, name=block.name, arguments=json.dumps(block.input))
        for block in response.content
        if block.type == "tool_use"
    ]
    return Completion(text=text, tool_calls=calls, finish_reason=str(response.stop_reason))
