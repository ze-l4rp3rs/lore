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
main.py ──► select_provider ──► run(provider, question, context) ──► RunResult
                                   │
              ┌────────────────────┴───────────────────────────────┐
              │ round 0..MAX_FIX_ROUNDS                            │
              │   generator  ask(...) ─► tool loop ─► draft        │
              │   reflector  ask(...) ─► JSON verdict              │
              │   approved? done : continue the generator's        │
              │                    conversation with the problems  │
              └────────────────────┬───────────────────────────────┘
                                   ▼
                       RunResult + runs/<timestamp>_<slug>.json / .md
```

| Path | Role |
|---|---|
| `main.py` | CLI entry point: reads the context file, picks a provider, prints `result.markdown` |
| `config.py` | Provider keys, models per role, limits, prompts |
| `src/providers/base.py` | Data classes and types shared by everything else |
| `src/providers/{groq,claude,gemini}.py` | One adapter each, exposing a single `complete(...)` |
| `src/providers/router.py` | Chooses a provider from the keys available; loads only that SDK |
| `src/tools/` | Tool registry: a function plus a `<name>.json` schema next to it |
| `src/workflow/tool_loop.py` | `ask(...)`: the bounded model → tools → model loop |
| `src/workflow/reflexion.py` | `run(...)`: the generate → review → fix workflow, plus `Check` and `RunResult` |
| `src/storage/run_logger.py` | Writes each run as JSON plus markdown |

## Data classes

Defined in [src/providers/base.py](src/providers/base.py), except `Check` and `RunResult`.

| Type | Kind | Fields | Used for |
|---|---|---|---|
| `ToolCall` | frozen dataclass | `id`, `name`, `arguments` (raw JSON text), `provider_data` | A tool request from the model, exactly as written |
| `Message` | `TypedDict` | `role`, `content`, optional `tool_calls`, `tool_call_id`, `name` | One turn of the shared conversation format |
| `Completion` | dataclass | `text`, `tool_calls`, `finish_reason`, `reasoning` | What one `complete()` call returns |
| `ToolTrace` | frozen dataclass | `name`, `arguments` (parsed dict), `result` | One tool run. `result` is exactly what the model was shown |
| `ModelReply` | dataclass | `text`, `tool_trace`, `reasoning`, `messages` | What `ask()` returns for one model call |
| `ToolMemo` | `dict[str, ToolTrace]` | key = tool name + sorted-JSON arguments | One result per (name, arguments) for a whole run |
| `Check` | dataclass (`reflexion.py`) | `draft`, `problems`, `reviewed` | The reflector's verdict on one draft. `reviewed` is False when its output was unusable |
| `RunResult` | dataclass (`reflexion.py`) | `question`, `answer`, `markdown`, `problems`, `status`, `log`, `rounds`, `elapsed_ms` | What `run()` returns. `to_dict()` is what gets logged |
| `Provider` | frozen dataclass | `name`, `complete`, `generator_model`, `reflector_model` | The chosen provider and its models |

`Completion` is the adapter-level result of a single model call. `ModelReply` is the workflow-level
result of `ask()`, which may involve several `Completion`s and tool runs. `provider_data` is opaque to
everything except the adapter that set it (Gemini thought signatures). `Message.name` is the tool's
name on a tool turn.

## How it works

### Providers

An adapter exposes `complete(model, messages, tools, tool_choice) -> Completion`. It makes exactly one
model call and never executes tools. Each adapter translates `Message` into its provider's format,
including tool turns, so the loop works the same through every provider:
- Claude: tool calls become `tool_use` blocks and results become `tool_result` blocks in a user turn.
- Gemini: tool calls become `function_call` parts (with the thought signature from `provider_data`) and
  results become `function_response` parts. Ids Gemini didn't issue are not sent back.
- Both merge consecutive same-role turns, because roles must alternate.

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

`run(provider, question, context="", user=None) -> RunResult`:
1. The generator answers from the context and its tools.
2. `check()` has the reflector review the draft. The reflector returns JSON,
   `{"approved": bool, "problems": [...]}`, and the parser tolerates fences or prose around it. The
   result is a `Check`:
   - unusable output, or the review raised: `reviewed=False`;
   - approved: no problems;
   - rejected with no listed problems: one generic problem is filled in.
3. If there are problems and rounds remain, the generator's own conversation (`reply.messages`) continues
   with only the problems listed and an instruction to change nothing else (`fix_request`). This repeats
   up to `MAX_FIX_ROUNDS`, and one `ToolMemo` is shared across all rounds.
4. The `RunResult` is built from the last `Check`:

   | Last check | `status` | `markdown` |
   |---|---|---|
   | not reviewed | `not checked` | draft + "could not be fact-checked" note |
   | has problems | `partly verified` | draft + list of flagged problems |
   | no problems | `verified` | draft |

   `rounds` is the number of drafts produced.
5. If the loop raises after at least one draft was checked, the error is logged and the run reports from
   the last `Check`. If it raises before any draft, the log is saved and the error is re-raised.

### Run logs

Each run writes `runs/<YYYYmmdd_HHMMSS>_<question-slug>.json` and a `.md` with `result.markdown`. `runs/` is
git-ignored. The JSON holds `question`, `steps` and `result` (`RunResult.to_dict()`). Steps are `start` (provider and models),
then `draft` (text, tool traces, reasoning), `review` and `fix` per round. A failed review adds a `review` step
with an `error`. A run that fails is still saved with an `error` step last. Dataclasses in the log are serialised with
`asdict`.
