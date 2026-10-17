import json
import os
from typing import Any

import config
from src.providers.base import Completion, Message, ToolCall, parse_arguments

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
    # Anthropic takes the system prompt separately, tool calls as tool_use blocks,
    # and tool results as tool_result blocks inside a user turn
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    chat: list[dict[str, Any]] = []
    for m in messages:
        if m["role"] == "system":
            continue
        if m["role"] == "assistant":
            role = "assistant"
            blocks = [{"type": "text", "text": m["content"]}] if m["content"].strip() else []
            blocks += [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": parse_arguments(c.arguments)}
                for c in m.get("tool_calls", [])
            ]
        elif m["role"] == "tool":
            role = "user"
            blocks = [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}]
        else:
            role = "user"
            blocks = [{"type": "text", "text": m["content"]}]
        if not blocks:
            continue
        # turns must alternate: fold consecutive same-role messages into one
        if chat and chat[-1]["role"] == role:
            chat[-1]["content"].extend(blocks)
        else:
            chat.append({"role": role, "content": blocks})
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
        extra["tool_choice"] = {"type": tool_choice}

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
