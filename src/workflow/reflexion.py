import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.providers.base import Message, Provider, ToolMemo, ToolTrace
from src.storage.run_logger import RunLogger
from src.validations import SourceRegistry, build_registry, render_context
from src.workflow.render import number_citations, render_markdown
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
    answer: str  # the final draft, with [[cite:...]] tokens
    markdown: str  # what a person reads
    sources: list[dict]  # cited sources, numbered as in the markdown
    problems: list[str]  # left unresolved after the last round
    status: str  # "verified", "partly verified", or "not checked"
    log: str
    rounds: int  # generator rounds actually run: the first draft plus each fix
    elapsed_ms: int  # wall-clock time of the whole run

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def format_request(
    question: str,
    registry: SourceRegistry
) -> str:
    return f"{render_context(registry)}\n\n<question>\n{question}\n</question>"


def format_tool_trace(
    traces: list[ToolTrace]
) -> str:
    if not traces:
        return "(no tool calls)"
    lines = []
    for trace in traces:
        arguments = json.dumps(trace.arguments, ensure_ascii=False)
        outcome = "sources " + ", ".join(trace.source_ids) if trace.source_ids else "(no results)"
        lines.append(f"- {trace.name}({arguments}) -> {outcome}")
    return "\n".join(lines)


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
    question: str,
    registry: SourceRegistry,
    draft: str,
    traces: list[ToolTrace],
    logger: RunLogger
) -> tuple[bool, list[str]] | None:
    # the reflector sees the same sources as the generator, plus which tool produced which source
    messages: list[Message] = [
        {"role": "system", "content": config.REFLECTOR_PROMPT},
        {"role": "user", "content": (
            f"{format_request(question, registry)}\n\n"
            f"<tool_calls>\n{format_tool_trace(traces)}\n</tool_calls>\n\n"
            f"<draft>\n{draft}\n</draft>"
        )},
    ]
    reply = ask(provider, provider.reflector_model, messages, registry, use_tools=False)
    parsed = parse_review(reply.text)
    logger.step("review", output=reply.text, reasoning=reply.reasoning, usable=parsed is not None)
    return parsed


def check(
    provider: Provider,
    question: str,
    registry: SourceRegistry,
    draft: str,
    traces: list[ToolTrace],
    logger: RunLogger
) -> Check:
    try:
        reviewed = review(provider, question, registry, draft, traces, logger)
    except Exception as caught:
        logger.step(
            "review",
            error=f"{type(caught).__name__}: {caught}",
            tools=getattr(caught, "tool_trace", []),
            reasoning=getattr(caught, "reasoning", ""),
        )
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
    registry = build_registry(context)
    memo: ToolMemo = {}  # one per run: a repeated tool call is answered from here
    traces: list[ToolTrace] = []
    checks: list[Check] = []
    logger.step("start", provider=provider.name, generator=provider.generator_model,
                reflector=provider.reflector_model, context_sources=list(registry.sources))

    try:
        messages: list[Message] = [
            {"role": "system", "content": config.GENERATOR_PROMPT},
            {"role": "user", "content": format_request(question, registry)},
        ]
        for round_number in range(config.MAX_FIX_ROUNDS + 1):
            # 1. generator: answer from the context and whatever its tools return
            reply = ask(provider, provider.generator_model, messages, registry, memo, user=user)
            traces += reply.tool_trace
            logger.step("draft", round=round_number, text=reply.text, tools=reply.tool_trace, reasoning=reply.reasoning)

            # 2. reflector: a verdict on the draft, as JSON the workflow can act on
            result = check(provider, question, registry, reply.text, traces, logger)
            checks.append(result)
            if not result.reviewed or not result.problems or round_number == config.MAX_FIX_ROUNDS:
                break

            # continue the same conversation (tool turns included) with only the problems,
            # so correct sentences are kept rather than rewritten
            request = fix_request(result)
            logger.step("fix", request=request)
            messages = reply.messages + [{"role": "user", "content": request}]
    except Exception as caught:
        logger.step("error", error=f"{type(caught).__name__}: {caught}")
        if not checks:
            logger.save()
            raise

    last = checks[-1]
    body, sources = number_citations(last.draft, registry)
    markdown = render_markdown(body, sources, last.problems, last.reviewed)
    if not last.reviewed:
        status = "not checked"
    elif last.problems:
        status = "partly verified"
    else:
        status = "verified"

    result = RunResult(
        question=question, answer=last.draft, markdown=markdown, sources=sources, problems=last.problems, status=status,
        log=logger.path + ".json", rounds=len(checks), elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    logger.save(result.to_dict(), markdown)
    return result
