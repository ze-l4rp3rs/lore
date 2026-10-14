# lore

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add at least one API key
python main.py orion.txt "Who owns the Keycloak rollout?"
```

Provider selection:
- One API key set: that provider is used.
- Several keys and a terminal: you are asked which one.
- Several keys and no terminal: `DEFAULT_PROVIDER` decides (from `.env` or `config.py`).
- No keys: the run fails with a message listing the env vars to set.

## Architecture

```
main.py ──► select_provider ──► reflexion(question, context)
                                   │
              ┌────────────────────┴───────────────────────────────┐
              │ round 0..MAX_FIX_ROUNDS                            │
              │   generator  ask(...) ─► tool loop ─► draft        │
              │   reflector  ask(...) ─► JSON verdict              │
              │   approved? done : continue the generator's        │
              │                    conversation with the problems  │
              └────────────────────┬───────────────────────────────┘
                                   ▼
                       answer + runs/<timestamp>_<slug>.json / .md
```

| Path | Role |
|---|---|
| `main.py` | CLI entry point: reads the context file, picks a provider, prints the answer |
| `config.py` | Provider keys, models per role, limits, prompts |
| `src/providers/base.py` | Data classes and types shared by everything else |
| `src/providers/{groq,claude,gemini}.py` | One adapter each, exposing a single `complete(...)` |
| `src/providers/router.py` | Chooses a provider from the keys available; loads only that SDK |
| `src/tools/` | Tool registry: a function plus a `<name>.json` schema next to it |
| `src/workflow/tool_loop.py` | `ask(...)`: the bounded model → tools → model loop |
| `src/workflow/reflexion.py` | The generate → review → fix workflow |
| `src/storage/run_logger.py` | Writes each run as JSON plus markdown |

## Data classes

All defined in [src/providers/base.py](src/providers/base.py).

| Type | Kind | Fields | Used for |
|---|---|---|---|
| `ToolCall` | frozen dataclass | `id`, `name`, `arguments` (raw JSON text) | A tool request from the model, exactly as written |
| `Message` | `TypedDict` | `role`, `content`, optional `tool_calls`, `tool_call_id` | One turn of the shared conversation format |
| `Completion` | dataclass | `text`, `tool_calls`, `finish_reason`, `reasoning` | What one `complete()` call returns |
| `ToolTrace` | frozen dataclass | `name`, `arguments` (parsed dict), `result` | One tool run. `result` is exactly what the model was shown |
| `ModelReply` | dataclass | `text`, `tool_trace`, `reasoning`, `messages` | What `ask()` returns for one model call |
| `ToolMemo` | `dict[str, ToolTrace]` | key = tool name + sorted-JSON arguments | One result per (name, arguments) for a whole run |
| `Provider` | frozen dataclass | `name`, `complete`, `generator_model`, `reflector_model` | The chosen provider and its models |

`Completion` is the adapter-level result of a single model call. `ModelReply` is the workflow-level
result of `ask()`, which may involve several `Completion`s and tool runs.

## How it works

### Providers

An adapter exposes `complete(model, messages, tools, tool_choice) -> Completion`. It makes exactly one
model call and never executes tools. Each adapter translates `Message` into its provider's format. Only
Groq replays tool turns so far (`TOOL_CALLING` in the router). The others are wrapped to answer without
tools.

### Tool loop (`ask`)

`ask(provider, model, messages, memo=None, user=None) -> ModelReply`:
- Works on a copy of `messages`; the caller's list is never mutated.
- Each step calls `complete()`. If the model asks for tools, each `ToolCall` runs through `run_tool` and
  the result is appended as a `tool` message. After `MAX_TOOL_STEPS` the last call has tools disabled,
  so the model must answer.
- Text written next to a tool call is dropped. The model must write the whole answer after the results.
- A bad call doesn't crash the run. An unknown tool, malformed arguments or a tool that raises becomes a
  `ToolTrace` whose result is `Tool error (<name>): <Type>: <msg>`, which the model sees. Failures are
  not memoised.
- A repeated call with the same name and arguments is answered from the `ToolMemo` without re-running
  the tool.
- Reasoning is kept out of the answer. It comes from `Completion.reasoning` plus any `<think>` text in
  the output, and ends up in `ModelReply.reasoning`.
- `ModelReply.messages` is the whole conversation including tool turns, so a caller can continue it.

### Reflexion workflow

1. The generator answers from the context and its tools.
2. The reflector gets the request plus the draft and returns JSON, `{"approved": bool, "problems": [...]}`.
   The parser tolerates fences or prose around it.
3. If not approved, the generator's own conversation (`reply.messages`) continues with only the problems
   listed and an instruction to change nothing else. This repeats up to `MAX_FIX_ROUNDS`, and one
   `ToolMemo` is shared across all rounds.
4. The final answer is the draft if approved, the draft plus a list of flagged problems if rounds ran
   out, or the draft plus a "could not be fact-checked" note if the reviewer's output was unusable.

### Run logs

Each run writes `runs/<YYYYmmdd_HHMMSS>_<question-slug>.json` and a `.md` with the answer. `runs/` is
git-ignored. The JSON holds `question`, `steps` and `result`. Steps are `start` (provider and models),
then `draft` (text, tool traces, reasoning), `review` and `fix` per round. A failed run is still saved
with an `error` step last, and the exception is re-raised. Dataclasses in the log are serialised with
`asdict`.
