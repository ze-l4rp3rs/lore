import json
import os
import secrets
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.providers.base import Completion, Message, ToolCall, parse_arguments

_client = None


def client():
    # created on first use, so this module imports (and its translation is testable) without the SDK
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=os.getenv(config.PROVIDER_KEYS["gemini"]))
    return _client


def to_gemini_tools(
    tools: list[dict]
) -> list[dict[str, Any]]:
    declarations = []
    for t in tools:
        function = t["function"]
        declaration: dict[str, Any] = {"name": function["name"], "description": function.get("description", "")}
        parameters = function.get("parameters")
        # Gemini rejects an OBJECT schema with no properties; a no-argument tool just omits it
        if parameters and parameters.get("properties"):
            declaration["parameters"] = parameters
        declarations.append(declaration)
    return [{"function_declarations": declarations}]


def to_gemini_contents(
    messages: list[Message]
) -> tuple[str, list[dict[str, Any]]]:
    # Gemini takes the system prompt separately and calls the assistant role "model"
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents: list[dict[str, Any]] = []
    api_ids: dict[str, bool] = {}  # our call id -> whether Gemini issued it (else it is ours; don't send it)
    for m in messages:
        if m["role"] == "system":
            continue
        if m["role"] == "assistant":
            role = "model"
            parts: list[dict[str, Any]] = [{"text": m["content"]}] if m["content"].strip() else []
            for c in m.get("tool_calls", []):
                data = c.provider_data or {}
                api_ids[c.id] = bool(data.get("has_id"))
                call: dict[str, Any] = {"name": c.name, "args": parse_arguments(c.arguments)}
                if api_ids[c.id]:
                    call["id"] = c.id
                part: dict[str, Any] = {"function_call": call}
                # Gemini 3 rejects a replayed function call without the signature it was issued with
                if data.get("thought_signature"):
                    part["thought_signature"] = data["thought_signature"]
                parts.append(part)
        elif m["role"] == "tool":
            role = "user"
            response: dict[str, Any] = {"name": m.get("name", ""), "response": {"result": m["content"]}}
            if api_ids.get(m["tool_call_id"]):
                response["id"] = m["tool_call_id"]
            parts = [{"function_response": response}]
        else:
            role = "user"
            parts = [{"text": m["content"]}]
        if not parts:
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})
    return system, contents


def complete(
    model: str,
    messages: list[Message],
    tools: list[dict] | None = None,
    tool_choice: str = "auto"
) -> Completion:
    system, contents = to_gemini_contents(messages)
    request_config: dict[str, Any] = {
        "system_instruction": system or None,
        "max_output_tokens": config.MAX_TOKENS,
        "temperature": config.TEMPERATURE,
    }
    if tools:
        request_config["tools"] = to_gemini_tools(tools)
        request_config["tool_config"] = {"function_calling_config": {"mode": tool_choice.upper()}}

    response = client().models.generate_content(model=model, contents=contents, config=request_config)

    candidate = response.candidates[0] if response.candidates else None
    parts = candidate.content.parts if candidate and candidate.content and candidate.content.parts else []
    text = "".join(p.text for p in parts if p.text and not p.thought)
    calls = []
    for p in parts:
        if p.function_call is None:
            continue
        calls.append(ToolCall(
            id=p.function_call.id or "gemini_" + secrets.token_hex(4),
            name=p.function_call.name or "",
            arguments=json.dumps(dict(p.function_call.args or {})),
            provider_data={"has_id": bool(p.function_call.id), "thought_signature": p.thought_signature},
        ))
    reason = candidate.finish_reason if candidate else None
    return Completion(text=text, tool_calls=calls, finish_reason=str(reason))
