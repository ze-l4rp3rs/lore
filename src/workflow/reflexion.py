import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import config
from src.workflow.tool_loop import ask


def reflexion(
    question: str,
    context: str
) -> str:
    request = f"<context>\n{context}\n</context>\n\n<question>\n{question}\n</question>"

    # 1. generator: answer from the context and whatever its tools return
    draft = ask(config.GROQ_MODEL, [
        {"role": "system", "content": config.GENERATOR_PROMPT},
        {"role": "user", "content": request},
    ])

    # 2. reflector: keep only what the context supports
    reviewed = ask(config.GROQ_MODEL, [
        {"role": "system", "content": config.REFLECTOR_PROMPT},
        {"role": "user", "content": f"{request}\n\n<draft>\n{draft}\n</draft>"},
    ])
    return reviewed.strip() or draft
