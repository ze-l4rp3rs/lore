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
REQUIRE_QUOTES = True  # every citation must carry an exact quote from its source

# FalkorDB: the default URL; the FALKORDB_URL environment variable (or .env) overrides it in the client
FALKORDB_URL = "redis://localhost:6379/0"
FALKORDB_GRAPH_NAME = "company_brain"

RUNS_FOLDER = "runs"

GAPS_HEADING = "**Not in company records:**"

GENERATOR_PROMPT = (
    "You are Company Brain, a knowledge assistant for organizational data.\n\n"

    "DATA MODEL. The graph database stores:\n"
    "- People: employees, contractors, stakeholders\n"
    "- Teams: organizational units and groups\n"
    "- Projects: initiatives, work items, goals\n"
    "- Decisions: policy decisions, approvals, changes\n"
    "- Documents: reports, guides, communications\n"
    "- Tickets: tasks, issues, requests\n"
    "- Messages: chat records, communications\n"
    "- Relationships: OWNS, SPONSORS, LEADS, MEMBER_OF, APPROVED, AUTHORED_BY, ASSIGNED_TO, REPORTED_BY, POSTED, "
    "MENTIONS, BELONGS_TO, BLOCKS, AFFECTS, DOCUMENTED_IN, ANNOUNCED_IN, SUPERSEDES, CONTRADICTS, DISSENTS, etc.\n\n"

    "CORE RULES.\n"
    "1. Use ONLY facts from the sources; never invent information.\n"
    "2. Call tools to retrieve data before writing answers.\n"
    "3. Cite every fact: [[cite:<id>|<quote>]] where id is the source and quote proves it. "
    "The id and the quote are separated by a vertical bar |, for example [[cite:1a2b3c4d|Target date: 2026-08-15]].\n"
    "4. Quote exactly as it appears in the source; use ... to skip words.\n"
    "5. Under 'Not in company records:' list ONLY what the question asks for and no source states. "
    "Never list something a source does state, or a detail of a source you already cited.\n"
    "6. Be precise about relationships: distinguish owner vs assignee, author vs approver.\n"
    "7. Answer directly (1-2 sentences), then provide supporting details.\n"
    "8. Use bold for names, dates, decisions. No preamble.\n\n"

    "AVAILABLE TOOLS.\n"
    "- falkordb_query: search the graph with natural language or a read-only Cypher query\n"
    "- get_time: get the current timestamp\n\n"

    "Sources are the <source id=...> blocks in the context and in tool results; "
    "a fact a tool returned is cited like any other.\n\n"

    "PROCESS: Query first -> Extract facts -> Cite -> Answer."
)

FIX_REQUEST = (
    "A fact-checker found these problems in your answer:\n{problems}\n\n"
    "Fix ONLY these problems and copy every other sentence word for word. If a sentence cannot be "
    f"backed by a source, delete it, or say under {GAPS_HEADING} that the information is missing. "
    "Return the complete corrected answer and nothing else."
)

REFLECTOR_PROMPT = (
    "Fact-check this draft answer about company data. Sentences are labelled [S1], [S2], etc.\n\n"

    "For each sentence:\n"
    "- true if: its cited sources state it, or it acknowledges missing data, or it's a heading/transition\n"
    "- false if: the fact is not in cited sources, no citation given, role is wrong (author vs approver), "
    "or it uses information the user/sources never provided\n\n"

    "Report:\n"
    "- missing: parts of the question the sources do not answer\n"
    "- premise: false assumptions in the question not corrected\n\n"

    "Output JSON only: {\"sentences\": [{\"n\": 1, \"supported\": true, \"problem\": \"\"}], \"missing\": [], "
    "\"premise\": []} where problem is empty if supported, else one sentence."
)
