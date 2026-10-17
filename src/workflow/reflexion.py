import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import config
from src.providers.base import Message, Provider, ToolMemo, ToolTrace
from src.storage.run_logger import RunLogger
from src.validations import (
    Draft,
    SourceRegistry,
    build_registry,
    mechanical_issues,
    parse_draft,
    render_context,
    repair_citations,
    strip_citations,
)
from src.workflow.render import number_citations, render_markdown
from src.workflow.tool_loop import ask

NO_ANSWER = "I couldn't find a verifiable answer to this in the company records."

@dataclass
class Check:
    """One draft after the code checks and the reflector's review."""
    draft: Draft
    issues: dict[int, list[str]]  # sentence number -> problems; these sentences are not trusted
    missing: list[str] = field(default_factory=list)  # parts of the question the records do not answer
    premise: list[str] = field(default_factory=list)  # false premises left uncorrected
    reviewed: bool = True  # False when the reflector's output could not be used

    def score(self) -> tuple[int, int, int]:
        # lower is better: a reviewed draft beats an unreviewed one, then fewest bad sentences, then uncorrected premises
        return (0 if self.reviewed else 1, len(self.issues), len(self.premise))

@dataclass
class RunResult:
    question: str
    answer: str  # final text with [[cite:...]] tokens, unsupported sentences removed
    markdown: str  # what a person reads
    sources: list[dict]  # cited sources, numbered as in the markdown
    unverified: list[dict]  # removed sentences: {"claim", "reason"}
    premise: list[str]
    missing: list[str]
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
        if trace.status != "ok":
            outcome = f"[{trace.status}: {trace.error}]"
        else:
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
    text: str,
    draft: Draft
) -> tuple[dict[int, list[str]], list[str], list[str]] | None:
    data = _json_object(text, "sentences")
    if data is None or not isinstance(data.get("sentences"), list):
        return None
    issues: dict[int, list[str]] = {}
    judged = set()
    for item in data["sentences"]:
        if not isinstance(item, dict):
            continue
        try:
            number = int(str(item.get("n", "")).lstrip("Ss"))
        except ValueError:
            continue
        if number not in draft.numbered:
            continue
        judged.add(number)
        if item.get("supported") is not True:
            issues[number] = [str(item.get("problem") or "").strip() or "the cited sources don't state this"]
    # a sentence the reflector skipped has not been checked, so it is not trusted either
    for number in draft.numbered.keys() - judged:
        issues[number] = ["the fact-checker did not confirm this"]
    return issues, _strings(data.get("missing")), _strings(data.get("premise"))

def review(
    provider: Provider,
    question: str,
    registry: SourceRegistry,
    draft: Draft,
    traces: list[ToolTrace],
    logger: RunLogger
) -> tuple[dict[int, list[str]], list[str], list[str]] | None:
    messages: list[Message] = [
        {"role": "system", "content": config.REFLECTOR_PROMPT},
        {"role": "user", "content": (
            f"{format_request(question, registry)}\n\n"
            f"<tool_calls>\n{format_tool_trace(traces)}\n</tool_calls>\n\n"
            f"<draft>\n{draft.labelled()}\n</draft>"
        )},
    ]
    for attempt in (1, 2):  # one retry when the reply is not usable JSON
        reply = ask(provider, provider.reflector_model, messages, registry, use_tools=False)
        parsed = parse_review(reply.text, draft)
        logger.step("review", attempt=attempt, output=reply.text, reasoning=reply.reasoning, usable=parsed is not None)
        if parsed is not None:
            return parsed
    return None

def check(
    provider: Provider,
    question: str,
    registry: SourceRegistry,
    text: str,
    traces: list[ToolTrace],
    logger: RunLogger
) -> Check:
    # 1. code: fix near-miss quotes and brackets, then find what is provably wrong
    text, repairs = repair_citations(text, registry)
    draft = parse_draft(text)
    issues = mechanical_issues(draft, registry)
    logger.step("check", repairs=repairs, issues=issues)

    # 2. reflector: does each sentence follow from its sources, and is anything unanswered?
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
        return Check(draft=draft, issues=issues, reviewed=False)
    judged, missing, premise = reviewed
    for number, problems in judged.items():
        issues.setdefault(number, []).extend(problems)
    return Check(draft=draft, issues=issues, missing=missing, premise=premise)

def fix_request(
    result: Check
) -> str:
    problems = [
        f'- "{strip_citations(result.draft.sentence(number))}": {"; ".join(found)}'
        for number, found in sorted(result.issues.items())
    ]
    problems += [f"- False premise in the question you did not correct: {item}" for item in result.premise]
    return config.FIX_REQUEST.format(problems="\n".join(problems))

def needs_fix(
    result: Check
) -> bool:
    # a gap in the records is reported, not fixed: the model cannot answer what the records lack
    return bool(result.issues or result.premise)

def _reader_reason(
    problems: list[str]
) -> str:
    # code-check messages mention source ids; people get a plain explanation instead
    readable = [p for p in problems if "cite" not in p and "source " not in p and "quote" not in p]
    if not readable and any("has no citation" in p for p in problems):
        return "no source was given for this"
    return "; ".join(readable) or "the quoted source doesn't say this"

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
            reply = ask(provider, provider.generator_model, messages, registry, memo, user=user)
            traces += [trace for trace in reply.tool_trace if not trace.cached]  # a reused result is already listed
            logger.step("draft", round=round_number, text=reply.text, tools=reply.tool_trace, reasoning=reply.reasoning)

            result = check(provider, question, registry, reply.text, traces, logger)
            checks.append(result)
            if not result.reviewed or not needs_fix(result) or round_number == config.MAX_FIX_ROUNDS:
                break

            # continue the same conversation (tool turns included) with the repaired draft and only
            # the problems, so correct sentences are kept rather than rewritten
            request = fix_request(result)
            logger.step("fix", request=request)
            messages = reply.messages[:-1] + [
                {"role": "assistant", "content": result.draft.text},
                {"role": "user", "content": request},
            ]
    except Exception as caught:
        logger.step("error", error=f"{type(caught).__name__}: {caught}")
        if not checks:
            logger.save()
            raise

    # the best draft wins, not the latest; its untrusted sentences are removed and listed
    best = min(reversed(checks), key=Check.score)
    drop = set(best.issues)  # unreviewed drafts only carry code-proven issues, which are removed anyway
    answer = best.draft.without(drop) or NO_ANSWER
    unverified = [
        {"claim": strip_citations(best.draft.sentence(number)), "reason": _reader_reason(best.issues[number])}
        for number in sorted(drop)
    ]
    body, sources = number_citations(answer, registry)
    markdown = render_markdown(body, sources, unverified, best.premise, best.missing, best.reviewed)
    if not best.reviewed:
        status = "not checked"
    elif unverified or best.premise:
        status = "partly verified"
    else:
        status = "verified"

    result = RunResult(
        question=question, answer=answer, markdown=markdown, sources=sources, unverified=unverified,
        premise=best.premise, missing=best.missing, status=status, log=logger.path + ".json",
        rounds=len(checks), elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    logger.save(result.to_dict(), markdown)
    return result
