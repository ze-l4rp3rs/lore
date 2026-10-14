import os

from dotenv import load_dotenv

import config

_client = None


def client():
    # created on first use, so this module imports without the SDK
    global _client
    if _client is None:
        from groq import Groq
        load_dotenv()
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


def complete(
    messages: list[dict]
) -> str:
    response = client().chat.completions.create(
        model=config.GROQ_MODEL,
        max_tokens=config.MAX_TOKENS,
        temperature=config.TEMPERATURE,
        messages=messages,
    )
    return response.choices[0].message.content or ""


def reflexion(
    question: str,
    context: str
) -> str:
    request = f"<context>\n{context}\n</context>\n\n<question>\n{question}\n</question>"

    # 1. generator: answer from the context only
    draft = complete([
        {"role": "system", "content": config.GENERATOR_PROMPT},
        {"role": "user", "content": request},
    ])

    # 2. reflector: keep only what the context supports
    reviewed = complete([
        {"role": "system", "content": config.REFLECTOR_PROMPT},
        {"role": "user", "content": f"{request}\n\n<draft>\n{draft}\n</draft>"},
    ])
    return reviewed.strip() or draft
