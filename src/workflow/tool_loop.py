import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.providers.base import Message, ModelReply, Provider, ToolCall, ToolMemo, ToolTrace
from src.tools import AVAILABLE_FUNCTIONS, TOOL_SCHEMAS, call_tool
from src.validations import Evidence, Source, SourceRegistry, render_sources

_THINK_BLOCK = re.compile(r"<(think|thinking)>.*?</\1>", re.IGNORECASE | re.DOTALL)
_THINK_END = re.compile(r"</(?:think|thinking)>", re.IGNORECASE)
_THINK_OPEN = re.compile(r"<(?:think|thinking)>", re.IGNORECASE)


def split_reasoning(
    text: str
) -> tuple[str, str]:
    # reasoning models sometimes write their thinking into the answer: as <think> blocks, ended by a
    # stray </think> whose opening tag was lost, or opened and never closed (cut off); keep only the answer
    reasoning = [match.group(0) for match in _THINK_BLOCK.finditer(text)]
    text = _THINK_BLOCK.sub("", text)
    ends = list(_THINK_END.finditer(text))
    if ends:
        reasoning.append(text[:ends[-1].start()])
        text = text[ends[-1].end():]
    opened = _THINK_OPEN.search(text)
    if opened:
        reasoning.append(text[opened.start():])
        text = text[:opened.start()]
    return text.strip(), "\n\n".join(part.strip() for part in reasoning if part.strip())


def memo_key(
    name: str,
    arguments: dict
) -> str:
    return name + json.dumps(arguments, sort_keys=True, default=str)


def register_result(
    name: str,
    arguments: dict,
    result: Any,
    registry: SourceRegistry
) -> list[Source]:
    # every tool result becomes citable: one source per Evidence item, otherwise one for the whole result
    if isinstance(result, Evidence):
        result = [result]
    if isinstance(result, list) and all(isinstance(item, Evidence) for item in result):
        return [registry.add(item) for item in result]
    label = f"{name}({json.dumps(arguments, ensure_ascii=False)})" if arguments else name
    return [registry.add(Evidence(kind="tool", label=label, text=str(result)))]


def run_tool(
    call: ToolCall,
    registry: SourceRegistry,
    memo: ToolMemo,
    user: Any
) -> ToolTrace:
    arguments: dict = {}
    try:
        parsed = json.loads(call.arguments or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("arguments must be a JSON object")
        arguments = parsed
        key = memo_key(call.name, arguments)
        if key in memo:
            # same tool + same arguments already ran this run: reuse, don't re-execute
            return memo[key]
        if call.name not in AVAILABLE_FUNCTIONS:
            raise KeyError(f"unknown tool {call.name!r}")
        sources = register_result(call.name, arguments, call_tool(call.name, arguments, user), registry)
    except Exception as caught:
        # never let a bad or unknown tool call kill the run; tell the model instead (and don't memoize)
        return ToolTrace(name=call.name, arguments=arguments, result=f"Tool error ({call.name}): {type(caught).__name__}: {caught}")

    trace = ToolTrace(
        name=call.name,
        arguments=arguments,
        result=render_sources(sources) if sources else "(no results)",
        source_ids=tuple(source.id for source in sources),
    )
    memo[key] = trace
    return trace


def ask(
    provider: Provider,
    model: str,
    messages: list[Message],
    registry: SourceRegistry,
    memo: ToolMemo | None = None,
    user: Any = None,
    use_tools: bool = True
) -> ModelReply:
    # work on a copy; the reply carries the full history so a follow-up can continue the conversation
    history = list(messages)
    tools = (TOOL_SCHEMAS or None) if use_tools else None
    memo = memo if memo is not None else {}
    tool_trace: list[ToolTrace] = []
    reasoning: list[str] = []

    try:
        for step in range(config.MAX_TOOL_STEPS + 1):
            # out of tool budget: the last call must answer from the results it already has
            tool_choice = "auto" if step < config.MAX_TOOL_STEPS else "none"
            completion = provider.complete(model, history, tools, tool_choice)
            text, leaked = split_reasoning(completion.text)
            reasoning += [part for part in (completion.reasoning.strip(), leaked) if part]

            if not completion.tool_calls:
                if text == "":
                    raise RuntimeError(f"Empty response from {model} (finish_reason = {completion.finish_reason}).")
                history.append({"role": "assistant", "content": text})
                return ModelReply(text=text, tool_trace=tool_trace, reasoning="\n\n".join(reasoning), messages=history)
            if tools is None or tool_choice == "none":
                raise RuntimeError(f"{model} called a tool when tools were not allowed.")

            # text written next to a tool call is dropped: the model must write the WHOLE
            # answer after the results arrive, otherwise only the tail is ever returned
            history.append({"role": "assistant", "content": "", "tool_calls": completion.tool_calls})
            for call in completion.tool_calls:
                trace = run_tool(call, registry, memo, user)
                tool_trace.append(trace)
                history.append({"role": "tool", "content": trace.result, "tool_call_id": call.id, "name": call.name})
    except Exception as caught:
        # the partial work is kept on the error, so a failed call can still be logged and debugged
        caught.tool_trace = tool_trace  # type: ignore[attr-defined]
        caught.reasoning = "\n\n".join(reasoning)  # type: ignore[attr-defined]
        raise

    raise AssertionError("unreachable: the last step never allows tools")
