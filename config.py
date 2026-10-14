# LLM Provider Configuration
# provider name -> env var that holds its API key (the router looks for these in .env)
PROVIDER_KEYS = {
    "groq": "GROQ_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

# provider name -> model used for each role; a different reflector model catches more of the
# generator's blind spots than the same model checking itself
MODELS = {
    "groq":   {"generator": "qwen/qwen3.8-27b",  "reflector": "qwen/qwen3.8-27b"},
    "claude": {"generator": "claude-sonnet-5-5", "reflector": "claude-sonnet-5-5"},
    "gemini": {"generator": "gemini-3.8-flash",  "reflector": "gemini-3.8-flash"},
}

# Default provider: used when several API keys are set and there is no terminal to ask on
# (the API server, pipes); the DEFAULT_PROVIDER environment variable overrides it
DEFAULT_PROVIDER = "groq"

MAX_TOKENS = 2000
TEMPERATURE = 0
MAX_FIX_ROUNDS = 2  # targeted fixes after the first draft
MAX_TOOL_STEPS = 6

RUNS_FOLDER = "runs"

GENERATOR_PROMPT = (
    "You are Company Brain, a knowledge assistant for organizational data.\n\n"

    "CORE RULES.\n"
    "1. Use ONLY facts from the sources; never invent information.\n"
    "2. For unknown information, say plainly what is missing.\n"
    "3. Be precise about relationships: distinguish owner vs assignee, author vs approver.\n"
    "4. Answer directly (1-2 sentences), then provide supporting details.\n"
    "5. Use bold for names, dates, decisions. No preamble."
)

FIX_REQUEST = (
    "A fact-checker found these problems in your answer:\n{problems}\n\n"
    "Fix ONLY these problems and copy every other sentence word for word. If a sentence cannot be "
    "backed by a source, delete it, or say that the information is missing. "
    "Return the complete corrected answer and nothing else."
)

REFLECTOR_PROMPT = (
    "Fact-check this draft answer about company data against the sources.\n\n"

    "A problem is: a fact the sources do not state, a role that is wrong (author vs approver, "
    "owner vs assignee), or information the user/sources never provided.\n\n"

    "Output JSON only: {\"approved\": true, \"problems\": []} where approved is false if there is any "
    "problem, and each problem is one sentence."
)
