from dataclasses import dataclass, field
from typing import Callable, Literal, NotRequired, Optional, TypedDict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text, exactly as the model wrote it


class Message(TypedDict):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: NotRequired[list[ToolCall]]  # assistant turn that requested tools
    tool_call_id: NotRequired[str]  # tool turn: the call it answers


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
class Provider:
    name: str
    complete: Complete
    generator_model: str
    reflector_model: str
