import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, NotRequired, Optional, TypedDict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text, exactly as the model wrote it
    provider_data: Any = None  # opaque extras the provider needs back on replay (e.g. Gemini thought signatures)


class Message(TypedDict):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: NotRequired[list[ToolCall]]  # assistant turn that requested tools
    tool_call_id: NotRequired[str]  # tool turn: the call it answers
    name: NotRequired[str]  # tool turn: the tool's name (Gemini needs it)


def parse_arguments(
    arguments: str
) -> dict:
    # a tool call's raw JSON text as a dict; anything that is not a JSON object becomes {}
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass
class Completion:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    reasoning: str = ""  # the model's thinking, when the provider returns it separately


# complete(model, messages, tools, tool_choice): ONE model call, no tool execution.
# tools are OpenAI-style function schemas or None; tool_choice is "auto" or "none"
Complete = Callable[[str, list[Message], Optional[list[dict]], str], Completion]


class RequestTooLarge(RuntimeError):
    """The request can never fit the provider's limits, so retrying is pointless."""


@dataclass(frozen=True)
class ToolTrace:
    name: str
    arguments: dict
    result: str  # exactly what the model was shown
    source_ids: tuple[str, ...] = ()  # registry sources this result created
    status: str = "ok"
    error: str = ""
    duration_ms: int = 0
    cached: bool = False  # True when the result was reused from an earlier call in this run


@dataclass
class ModelReply:
    text: str
    tool_trace: list[ToolTrace] = field(default_factory=list)
    reasoning: str = ""  # kept out of the answer, logged for debugging
    messages: list[Message] = field(default_factory=list)  # the whole conversation, tool turns included


# one tool result per (name, arguments) for the whole run, so a repeated call is reused, not re-run
ToolMemo = dict[str, ToolTrace]


@dataclass(frozen=True)
class Provider:
    name: str
    complete: Complete
    generator_model: str
    reflector_model: str
