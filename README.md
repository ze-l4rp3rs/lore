# lore

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add at least one API key
python main.py -c orion.txt "Who owns the Keycloak rollout?"
```

- The question is the positional argument, or is prompted for when left out. `-c/--context` is an
  optional context file. It is split into sources at its `[kind: label, date]` header lines.
- The CLI prints the structured JSON response (see [Response](#response)). The readable version, with
  numbered footnotes, is written to `runs/*.md`.

Provider selection:
- One API key set: that provider is used.
- Several keys and a terminal: you are asked which one.
- Several keys and no terminal: `DEFAULT_PROVIDER` decides (from `.env` or `config.py`).
- No keys: the run fails with a message listing the env vars to set.

## Status

The project follows the 15 steps in [docs/build-plan.md](docs/build-plan.md); design docs are in
[docs/](docs/README.md).

**Done**
- Question answering over a context file (generator and reflector models) with fix rounds.
- Tool calling with a registry, a bounded loop and a per-run tool memo. One tool exists: `get_time`.
- Three provider adapters (Groq, Claude, Gemini) with tool calling, and automatic provider selection.
- Citations: every fact carries a checked quote, and the answer is rendered with numbered footnotes.
- Verification: code-side citation checks, then a per-sentence review by the reflector. Unsupported
  sentences are removed and listed.
- Structured response (`src/api/response.py`) and JSON plus markdown run logs.

**Next: FalkorDB and synthetic data** (build-plan steps 9 and 10)
1. **Synthetic company dataset** with deliberate traps: superseded and contradicting decisions,
   reassignments, a strategy document that later decisions made stale, dissent, and a question with a
   false premise. Include dataset checks (section counts, every reference resolves).
2. **FalkorDB as the graph database**, run in a container with a health check. Keys are supplied at run
   time, never built into an image.
3. **Graph client** (`src/retrieval/`): read-only, parameterised queries that return named fields. Writes
   go through a separate, ingestion-only path.
4. **Ingestion** (`src/ingestion/`): loads the dataset into the graph. A second run must change nothing,
   and everything written must appear in the graph schema description ([docs/schema.md](docs/schema.md),
   [docs/ingestion.md](docs/ingestion.md)).
5. **Graph tools** ([docs/tools.md](docs/tools.md)): general graph search, ownership lookup, expertise
   lookup, decision tracing and timelines. Each returns `Evidence` items, so every graph record becomes
   a citable source.

**Later:** web API, a configuration file, history and freshness status, incremental updates, evaluation
and proposed actions (steps 8 and 11 to 15).

**Known gaps**
- There are no automated tests in the repo yet. The build plan calls for tests against simulated models,
  never a real model service.
- Only one tool exists, and its output isn't graph data yet.
- The Groq free tier is rate limited, so a run can pause and retry.

## Architecture

```
main.py ──► select_provider ──► run(provider, question, context) ──► RunResult ──► build_response ──► JSON
                                   │
        ┌──────────────────────────┴─────────────────────────────────┐
        │ registry = build_registry(context)   (one source per record)│
        │ round 0..MAX_FIX_ROUNDS                                      │
        │   generator  ask(...) ─► tool loop ─► draft with citations   │
        │   check:     repair syntax ─► code checks ─► reflector       │
        │   problems?  continue the conversation with only the issues  │
        └──────────────────────────┬─────────────────────────────────┘
                                   ▼
          best draft, unsupported sentences removed ─► runs/<timestamp>_<slug>.json / .md
```

| Path | Role |
|---|---|
| `main.py` | CLI entry point: reads the context file, picks a provider, prints the JSON response |
| `config.py` | Provider keys, models per role, limits, prompts |
| `src/providers/base.py` | Data classes and types shared by everything else |
| `src/providers/{groq,claude,gemini}.py` | One adapter each, exposing a single `complete(...)` |
| `src/providers/router.py` | Chooses a provider from the keys available; loads only that SDK |
| `src/tools/` | Tool registry: a function plus a `<name>.json` schema next to it |
| `src/validations/sources.py` | `Evidence`, `Source`, `SourceRegistry`; renders sources as `<source id=...>` blocks |
| `src/validations/citations.py` | Citation syntax: the `[[cite:<id>\|<quote>]]` pattern, quote matching, syntax repair |
| `src/validations/checks.py` | Splits a draft into numbered sentences and finds problems code can prove |
| `src/workflow/tool_loop.py` | `ask(...)`: the bounded model → tools → model loop |
| `src/workflow/reflexion.py` | `run(...)`: the generate → check → fix workflow, plus `Check` and `RunResult` |
| `src/workflow/render.py` | Numbers citations and renders the readable markdown with a source list |
| `src/api/response.py` | `build_response(result)`: the one JSON shape the CLI (and later the API) returns |
| `src/storage/run_logger.py` | Writes each run as JSON plus markdown |
| `src/ingestion/`, `src/retrieval/` | Empty. Reserved for the graph work above |

## Data classes

Defined in [src/providers/base.py](src/providers/base.py) unless noted.

| Type | Kind | Fields | Used for |
|---|---|---|---|
| `ToolCall` | frozen dataclass | `id`, `name`, `arguments` (raw JSON text), `provider_data` | A tool request from the model, exactly as written |
| `Message` | `TypedDict` | `role`, `content`, optional `tool_calls`, `tool_call_id`, `name` | One turn of the shared conversation format |
| `Completion` | dataclass | `text`, `tool_calls`, `finish_reason`, `reasoning` | What one `complete()` call returns |
| `ToolTrace` | frozen dataclass | `name`, `arguments`, `result`, `source_ids`, `status`, `error`, `duration_ms`, `cached` | One tool run. `result` is exactly what the model was shown |
| `ModelReply` | dataclass | `text`, `tool_trace`, `reasoning`, `messages` | What `ask()` returns for one model call |
| `ToolMemo` | `dict[str, ToolTrace]` | key = tool name + sorted-JSON arguments | One result per (name, arguments) for a whole run |
| `Provider` | frozen dataclass | `name`, `complete`, `generator_model`, `reflector_model` | The chosen provider and its models |
| `Evidence` | frozen dataclass (`sources.py`) | `kind`, `label`, `text`, `date`, `url`, `ref`, `meta` | What a tool returns: one citable piece of text |
| `Source` | frozen dataclass (`sources.py`) | the `Evidence` fields plus a per-run random `id` | An entry in the registry; the id is what the model cites |
| `SourceRegistry` | dataclass (`sources.py`) | `sources`, `add()`, `by_id()` | All citable sources of one run. The same `ref` maps to the same source |
| `Draft` | dataclass (`checks.py`) | `text`, `lines`, `numbered` | An answer split into lines and numbered sentences `S1, S2, ...` |
| `Check` | dataclass (`reflexion.py`) | `draft`, `issues`, `missing`, `premise`, `reviewed` | The verdict on one draft. `issues` maps sentence number to problems |
| `RunResult` | dataclass (`reflexion.py`) | `question`, `answer`, `markdown`, `sources`, `unverified`, `premise`, `missing`, `status`, `log`, `rounds`, `elapsed_ms` | What `run()` returns. `to_dict()` is what gets logged |

`Completion` is the adapter-level result of one model call. `ModelReply` is the workflow-level result
of `ask()`, which may involve several `Completion`s and tool runs. `provider_data` is opaque to
everything except the adapter that set it (Gemini thought signatures).

## How it works

### Providers

An adapter exposes `complete(model, messages, tools, tool_choice) -> Completion`. It makes exactly one
model call and never executes tools. Each adapter translates `Message` into its provider's format,
including tool turns, so the loop works the same through every provider:
- Claude: tool calls become `tool_use` blocks and results become `tool_result` blocks in a user turn.
- Gemini: tool calls become `function_call` parts (with the thought signature from `provider_data`) and
  results become `function_response` parts. Ids Gemini didn't issue are not sent back.
- Groq: with `tool_choice="none"` no tools are sent at all, because a model that still writes a tool
  call would make Groq reject the request.
- Claude and Gemini merge consecutive same-role turns, because roles must alternate.

### Sources and citations

- `build_registry(context)` makes one `Source` per record in the context file. Each source gets a random
  8-hex id for this run, so retrieved text can't forge a real citation id.
- The model sees sources as `<source id=... type=... label=... date=...>` blocks. Structural tags inside
  source text are neutralised.
- The model cites every fact as `[[cite:<id>|<exact quote>]]`. Quotes may use `...` to skip words.
- Tool results become sources too: an `Evidence` item becomes its own source, any other result becomes
  one source holding the whole result. Failures never become sources.

### Tool loop (`ask`)

`ask(provider, model, messages, registry, memo=None, user=None, use_tools=True) -> ModelReply`:
- Works on a copy of `messages`; the caller's list is never mutated.
- Each step calls `complete()`. If the model asks for tools, each `ToolCall` runs through `run_tool`,
  registers its result in the registry and appends it as a `tool` message. After `MAX_TOOL_STEPS` the
  last call has tools disabled, so the model must answer.
- Text written next to a tool call is dropped. The model must write the whole answer after the results.
- A bad call doesn't crash the run. An unknown tool, malformed arguments or a tool that raises becomes a
  `ToolTrace` with `status="error"`, which the model also sees. Failures are not memoised.
- A repeated call with the same name and arguments is answered from the `ToolMemo` (`cached=True`)
  without re-running the tool.
- Reasoning is kept out of the answer. It comes from `Completion.reasoning` plus any `<think>` text in
  the output, and ends up in `ModelReply.reasoning`.
- If the loop raises, the exception carries `tool_trace` and `reasoning`, so the failed call can still be
  logged.
- The reflector runs with `use_tools=False`: it only checks the draft against the sources.

### Reflexion workflow

`run(provider, question, context="", user=None) -> RunResult`. Each round:

1. **Generator** answers from the sources and its tools.
2. **Repair** (`repair_citations`): fixes near-miss syntax without a model call. A citation one bracket
   short is closed, and a separator other than `|` (`#`, `>`, `→`, `:`) is rewritten to `|`. Quotes are
   never altered.
3. **Code checks** (`mechanical_issues`): per sentence, flags
   - a citation of an unknown source id;
   - a quote that is not in its source, or a citation with no quote (`REQUIRE_QUOTES`);
   - an uncited sentence that states a fact;
   - a malformed citation, a fake source link or plain-text source label;
   - leaked reasoning notes.

   Sentences under the "Not in company records:" heading state missing information and need no citation.
4. **Reflector** (`review`) sees the sources, the tool calls and the draft with numbered sentences. It
   returns JSON: `{"sentences": [{"n", "supported", "problem"}], "missing": [...], "premise": [...]}`.
   An unusable reply is retried once. A sentence it skips is treated as unconfirmed.
5. **Fix:** if there are issues or an uncorrected false premise, and rounds remain, the generator's own
   conversation continues with the repaired draft and only the problems listed, up to `MAX_FIX_ROUNDS`.
   A gap in the records (`missing`) is reported but never triggers a fix.

After the loop, the best draft wins (a reviewed draft beats an unreviewed one, then fewest bad
sentences). Its untrusted sentences are removed and listed in `unverified`. If nothing is left, the answer
is a fixed "couldn't find a verifiable answer" line.

| Outcome | `status` |
|---|---|
| reviewer output unusable | `not checked` |
| sentences removed, or a false premise left uncorrected | `partly verified` |
| otherwise | `verified` |

If the loop raises after at least one draft was checked, the error is logged and the run reports from
the best draft so far. If it raises before any draft, the log is saved and the error is re-raised.

### Response

`build_response(result)` returns the JSON the CLI prints and the web API will return:

| Field | Contents |
|---|---|
| `answer` | The answer with a `[[<id>]]` marker after each cited fact |
| `references` | One per cited source: `id`, `number`, `type`, `title`, `excerpt`, `quotes`, `date`, `url`, `nodeId`, `meta` |
| `status` | `verified`, `partly verified` or `not checked` |
| `unverified` | Removed sentences, each with a plain-language reason |
| `missing` | Parts of the question the records don't answer |
| `premise` | False assumptions in the question |
| `metadata` | `rounds`, `approved` (status is `verified`), `processingTimeMs` |

See [docs/api.md](docs/api.md) for the fields that come later (freshness status, proposed actions).

### Run logs

Each run writes `runs/<YYYYmmdd_HHMMSS>_<question-slug>.json` and a `.md` with `result.markdown`.
`runs/` is git-ignored. The JSON holds `question`, `steps` and `result` (`RunResult.to_dict()`).
Steps are `start` (provider, models, context sources), then per round `draft` (text, tool traces,
reasoning), `check` (repairs and code-found issues), `review` (reflector output, attempt, usable) and
`fix`. A failed review adds a `review` step with an `error`. A run that fails is still saved with an
`error` step last. Dataclasses in the log are serialised with `asdict`.
