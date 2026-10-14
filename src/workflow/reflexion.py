import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
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
    request: str,
    draft: str
) -> tuple[bool, list[str]] | None:
    return parse_review(ask(config.GROQ_MODEL, [
        {"role": "system", "content": config.REFLECTOR_PROMPT},
        {"role": "user", "content": f"{request}\n\n<draft>\n{draft}\n</draft>"},
    ]))


def _log_run(question: str, context: str, result: str, verdict, duration: float) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question[:100] + ("..." if len(question) > 100 else ""),
        "context_length": len(context),
        "result_preview": result[:200] + ("..." if len(result) > 200 else ""),
        "duration_seconds": round(duration, 3),
        "verdict_approved": verdict[0] if verdict else None,
        "verdict_problems": verdict[1] if verdict else None,
    }
    log_path = os.path.join(os.path.dirname(__file__), "..", "run_logs")
    os.makedirs(log_path, exist_ok=True)
    log_file = os.path.join(log_path, "run_history.jsonl")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def reflexion(
    question: str,
    context: str
) -> str:
    start = time.time()
    request = f"<context>\n{context}\n</context>\n\n<question>\n{question}\n</question>"
    messages: list[dict] = [
        {"role": "system", "content": config.GENERATOR_PROMPT},
        {"role": "user", "content": request},
    ]

    for round_number in range(config.MAX_FIX_ROUNDS + 1):
        # 1. generator: answer from the context and whatever its tools return
        draft = ask(config.GROQ_MODEL, messages)

        # 2. reflector: a verdict on the draft, as JSON the workflow can act on
        verdict = review(request, draft)
        if verdict is None or verdict[0] or round_number == config.MAX_FIX_ROUNDS:
            break

        # continue the same conversation (tool turns included) with only the problems,
        # so correct sentences are kept rather than rewritten
        problems = "\n".join(f"- {problem}" for problem in verdict[1])
        messages.append({"role": "user", "content": config.FIX_REQUEST.format(problems=problems)})

    duration = time.time() - start
    if verdict is None:
        result = f"{draft}\n\n(This answer could not be fact-checked.)"
    else:
        approved, problems = verdict
        if approved:
            result = draft
        else:
            result = draft + "\n\nThe fact-checker flagged:\n" + "\n".join(f"- {problem}" for problem in problems)

    _log_run(question, context, result, verdict, duration)
    return result
