import os
import re
import time
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.providers.base import Completion, Message, RequestTooLarge, ToolCall

RATE_LIMIT_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 20

_OUTPUT_LIMIT = re.compile(r"output tokens per minute.*?Limit (\d+)", re.IGNORECASE | re.DOTALL)

_client = None
_max_tokens_cap: int | None = None  # learned from a "request too large" error; kept for the whole run


def client():
    # created on first use, so this module imports (and its translation is testable) without the SDK
    global _client
    if _client is None:
        from groq import Groq
        _client = Groq(api_key=os.getenv(config.PROVIDER_KEYS["groq"]))
    return _client


def to_groq_messages(
    messages: list[Message]
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            converted.append({
                "role": "assistant",
                "content": m["content"],
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                    for c in m["tool_calls"]
                ],
            })
        elif m["role"] == "tool":
            converted.append({"role": "tool", "content": m["content"], "tool_call_id": m["tool_call_id"]})
        else:
            converted.append({"role": m["role"], "content": m["content"]})
    return converted


def shrink_max_tokens(
    error: str,
    current: int
) -> int:
    # "Limit 1000" on output tokens per minute: ask for a bit less than the cap, or 0 if that can't help
    match = _OUTPUT_LIMIT.search(error)
    smaller = int(int(match.group(1)) * 0.9) if match else 0
    return smaller if 0 < smaller < current else 0


def create_with_retry(
    **kwargs: Any
):
    global _max_tokens_cap
    from groq import RateLimitError

    # per-minute limits clear on their own; wait and retry instead of killing the run
    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        try:
            return client().chat.completions.create(**kwargs)
        except RateLimitError as caught:
            # "too large" means this single request is over a per-minute cap: waiting can't help,
            # but asking for fewer output tokens can
            if "too large" in str(caught).lower():
                smaller = shrink_max_tokens(str(caught), kwargs.get("max_tokens", 0))
                if smaller:
                    print(f"Groq output cap hit; retrying with max_tokens={smaller}.")
                    kwargs["max_tokens"] = _max_tokens_cap = smaller
                    continue
                raise RequestTooLarge(
                    f"Request is larger than Groq allows per minute; lower config.MAX_TOKENS "
                    f"or shorten the context. ({caught})"
                ) from caught
            if attempt == RATE_LIMIT_RETRIES:
                raise
            wait = RATE_LIMIT_WAIT_SECONDS * attempt
            print(f"Groq rate limit hit; waiting {wait}s (retry {attempt}/{RATE_LIMIT_RETRIES - 1})...")
            time.sleep(wait)


def complete(
    model: str,
    messages: list[Message],
    tools: list[dict] | None = None,
    tool_choice: str = "auto"
) -> Completion:
    extra: dict[str, Any] = {"tools": tools, "tool_choice": tool_choice} if tools else {}
    max_tokens = min(config.MAX_TOKENS, _max_tokens_cap or config.MAX_TOKENS)
    response = create_with_retry(
        model=model,
        max_tokens=max_tokens,
        temperature=config.TEMPERATURE,
        messages=to_groq_messages(messages),
        **extra,
    )
    choice = response.choices[0]
    message = choice.message
    calls = [
        ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments or "{}")
        for c in message.tool_calls or []
    ]
    return Completion(
        text=message.content or "",
        tool_calls=calls,
        finish_reason=str(choice.finish_reason),
        reasoning=getattr(message, "reasoning", None) or "",
    )
