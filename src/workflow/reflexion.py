import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.providers.base import Message, Provider, ToolMemo
from src.storage.run_logger import RunLogger
from src.workflow.tool_loop import ask


@dataclass
class Check:
    """One draft after the reflector's review."""
    draft: str
    problems: list[str] = field(default_factory=list)  # what the reflector found wrong with it
    reviewed: bool = True  # False when the reflector's output could not be used


@dataclass
class RunResult:
    question: str
    answer: str  # the final draft
    markdown: str  # what a person reads
    problems: list[str]  # left unresolved after the last round
    status: str  # "verified", "partly verified", or "not checked"
    log: str
    rounds: int  # generator rounds actually run: the first draft plus each fix
    elapsed_ms: int  # wall-clock time of the whole run

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def check(
    provider: Provider,
    request: str,
    draft: str,
    logger: RunLogger
) -> Check:
    try:
        reviewed = review(provider, request, draft, logger)
    except Exception as caught:
        logger.step("review", error=f"{type(caught).__name__}: {caught}")
        reviewed = None
    if reviewed is None:
        return Check(draft=draft, reviewed=False)
    approved, problems = reviewed
    return Check(draft=draft, problems=[] if approved else problems or ["the fact-checker rejected this answer"])


def fix_request(
    result: Check
) -> str:
    return config.FIX_REQUEST.format(problems="\n".join(f"- {problem}" for problem in result.problems))


def run(
    provider: Provider,
    question: str,
    context: str = "",
    user: Any = None
) -> RunResult:
    started = time.perf_counter()
    logger = RunLogger(question)
    request = f"<context>\n{context}\n</context>\n\n<question>\n{question}\n</question>"
    memo: ToolMemo = {}  # one per run: a repeated tool call is answered from here
    checks: list[Check] = []
    logger.step("start", provider=provider.name, generator=provider.generator_model,
                reflector=provider.reflector_model)

    try:
        messages: list[Message] = [
            {"role": "system", "content": config.GENERATOR_PROMPT},
            {"role": "user", "content": request},
        ]
        for round_number in range(config.MAX_FIX_ROUNDS + 1):
            # 1. generator: answer from the context and whatever its tools return
            reply = ask(provider, provider.generator_model, messages, memo, user=user)
            logger.step("draft", round=round_number, text=reply.text, tools=reply.tool_trace, reasoning=reply.reasoning)

            # 2. reflector: a verdict on the draft, as JSON the workflow can act on
            result = check(provider, request, reply.text, logger)
            checks.append(result)
            if not result.reviewed or not result.problems or round_number == config.MAX_FIX_ROUNDS:
                break

            # continue the same conversation (tool turns included) with only the problems,
            # so correct sentences are kept rather than rewritten
            request_fix = fix_request(result)
            logger.step("fix", request=request_fix)
            messages = reply.messages + [{"role": "user", "content": request_fix}]
    except Exception as caught:
        logger.step("error", error=f"{type(caught).__name__}: {caught}")
        if not checks:
            logger.save()
            raise

    last = checks[-1]
    if not last.reviewed:
        status = "not checked"
        markdown = f"{last.draft}\n\n(This answer could not be fact-checked.)"
    elif last.problems:
        status = "partly verified"
        markdown = last.draft + "\n\nThe fact-checker flagged:\n" + "\n".join(f"- {p}" for p in last.problems)
    else:
        status = "verified"
        markdown = last.draft

    result = RunResult(
        question=question, answer=last.draft, markdown=markdown, problems=last.problems, status=status,
        log=logger.path + ".json", rounds=len(checks), elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    logger.save(result.to_dict(), markdown)
    return result
