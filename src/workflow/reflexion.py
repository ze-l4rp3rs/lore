import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.providers.base import Message, Provider, ToolMemo
from src.storage.run_logger import RunLogger
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
    draft: str,
    logger: RunLogger
) -> tuple[bool, list[str]] | None:
    reply = ask(provider, provider.reflector_model, [
        {"role": "system", "content": config.REFLECTOR_PROMPT},
        {"role": "user", "content": f"{request}\n\n<draft>\n{draft}\n</draft>"},
    ])
    parsed = parse_review(reply.text)
    logger.step("review", output=reply.text, reasoning=reply.reasoning, usable=parsed is not None)
    return parsed


def reflexion(
    provider: Provider,
    question: str,
    context: str
) -> str:
    logger = RunLogger(question)
    request = f"<context>\n{context}\n</context>\n\n<question>\n{question}\n</question>"
    memo: ToolMemo = {}  # one per run: a repeated tool call is answered from here
    logger.step("start", provider=provider.name, generator=provider.generator_model,
                reflector=provider.reflector_model)

    try:
        messages: list[Message] = [
            {"role": "system", "content": config.GENERATOR_PROMPT},
            {"role": "user", "content": request},
        ]
        for round_number in range(config.MAX_FIX_ROUNDS + 1):
            # 1. generator: answer from the context and whatever its tools return
            reply = ask(provider, provider.generator_model, messages, memo)
            draft = reply.text
            logger.step("draft", round=round_number, text=draft, tools=reply.tool_trace, reasoning=reply.reasoning)

            # 2. reflector: a verdict on the draft, as JSON the workflow can act on
            verdict = review(provider, request, draft, logger)
            if verdict is None or verdict[0] or round_number == config.MAX_FIX_ROUNDS:
                break

            # continue the same conversation (tool turns included) with only the problems,
            # so correct sentences are kept rather than rewritten
            problems = "\n".join(f"- {problem}" for problem in verdict[1])
            fix = config.FIX_REQUEST.format(problems=problems)
            logger.step("fix", request=fix)
            messages = reply.messages + [{"role": "user", "content": fix}]
    except Exception as caught:
        logger.step("error", error=f"{type(caught).__name__}: {caught}")
        logger.save()
        raise

    if verdict is None:
        answer = f"{draft}\n\n(This answer could not be fact-checked.)"
    elif verdict[0]:
        answer = draft
    else:
        answer = draft + "\n\nThe fact-checker flagged:\n" + "\n".join(f"- {problem}" for problem in verdict[1])
    logger.save({"answer": answer}, answer)
    return answer
