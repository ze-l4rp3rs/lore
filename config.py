# LLM Provider Configuration
GROQ_MODEL = "qwen/qwen3.8-27b"

MAX_TOKENS = 2000
TEMPERATURE = 0

GENERATOR_PROMPT = (
    "You are Company Brain, a knowledge assistant for organizational data.\n\n"
    "Answer the question using ONLY the context. Do not add anything the context does not say. "
    "If the context does not contain the answer, say so."
)

REFLECTOR_PROMPT = (
    "Fact-check this draft answer about company data against the context.\n\n"
    "Remove every claim the context does not support and keep everything else as written. "
    "Return the corrected answer and nothing else."
)
