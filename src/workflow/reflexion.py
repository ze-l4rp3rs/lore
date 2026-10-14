import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.providers.base import Message, Provider
from src.workflow.tool_loop import ask


def _json_object(
    text: str,
    key: str
) -> dict | None:
    # the reflector should return bare JSON, but tolerate fences or stray prose around it
    decoder = json.JSONDecoder()
    found = None
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and key in value:
            found = value
    return found


def _strings(
    value: Any
) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def parse_review(
    text: str
) -> tuple[bool, list[str]] | None:
    data = _json_object(text, "approved")
    if data is None:
        return None
    problems = _strings(data.get("problems"))
    return data.get("approved") is True and not problems, problems


def review(
    provider: Provider,
    request: str,
    draft: str
) -> tuple[bool, list[str]] | None:
    return parse_review(ask(provider, provider.reflector_model, [
        {"role": "system", "content": config.REFLECTOR_PROMPT},
        {"role": "user", "content": f"{request}\n\n<draft>\n{draft}\n</draft>"},
    ]))


def reflexion(
    provider: Provider,
    question: str,
    context: str
) -> str:
    request = f"<context>\n{context}\n</context>\n\n<question>\n{question}\n</question>"
    messages: list[Message] = [
        {"role": "system", "content": config.GENERATOR_PROMPT},
        {"role": "user", "content": request},
    ]

    for round_number in range(config.MAX_FIX_ROUNDS + 1):
        # 1. generator: answer from the context and whatever its tools return
        draft = ask(provider, provider.generator_model, messages)

        # 2. reflector: a verdict on the draft, as JSON the workflow can act on
        verdict = review(provider, request, draft)
        if verdict is None or verdict[0] or round_number == config.MAX_FIX_ROUNDS:
            break

        # continue the same conversation (tool turns included) with only the problems,
        # so correct sentences are kept rather than rewritten
        problems = "\n".join(f"- {problem}" for problem in verdict[1])
        messages.append({"role": "user", "content": config.FIX_REQUEST.format(problems=problems)})

    if verdict is None:
        return f"{draft}\n\n(This answer could not be fact-checked.)"
    approved, problems = verdict
    if approved:
        return draft
    return draft + "\n\nThe fact-checker flagged:\n" + "\n".join(f"- {problem}" for problem in problems)
