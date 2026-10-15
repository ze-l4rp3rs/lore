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

To query the company graph instead of a context file, start FalkorDB, load the dataset, then ask:

```bash
scripts/db.sh up        # FalkorDB on localhost:6379, browser UI on http://localhost:3000
scripts/db.sh ingest    # loads company_brain_dataset.json
python main.py "Who owns the Platform Redesign project?"
scripts/db.sh down      # clean exit (keeps the data); `scripts/db.sh reset` also deletes it
```

- The ingest script **clears the whole `company_brain` graph** before loading, so a second run rebuilds
  the same graph. Point `FALKORDB_GRAPH_NAME` in `config.py` elsewhere if that name is already in use.
- If port 6379 or 3000 is taken, set `FALKORDB_PORT` / `FALKORDB_BROWSER_PORT` (and `FALKORDB_URL` for the
  agent). The ports are bound to `localhost` only, and the image has no password.
- With no context file and no database, the model has nothing to answer from.

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
- Tool calling with a registry, a bounded loop and a per-run tool memo. Two tools: `get_time` and `falkordb_query`.
- Three provider adapters (Groq, Claude, Gemini) with tool calling, and automatic provider selection.
- Citations: every fact carries a checked quote, and the answer is rendered with numbered footnotes.
- Verification: code-side citation checks, then a per-sentence review by the reflector. Unsupported
  sentences are removed and listed.
- Structured response (`src/api/response.py`) and JSON plus markdown run logs.
- FalkorDB graph: client, schema, idempotent ingestion of `company_brain_dataset.json` (the synthetic
  "Meridian" company: 144 nodes, 321 edges), run through `docker-compose.yml` and `scripts/db.sh`.
- `falkordb_query` tool: natural language or read-only Cypher. A row that is one node becomes a source of
  its real type, title, date and node id, so the same node found twice is one source.
- Checked live on Groq against the running graph: questions on ownership and on budget decisions
  (superseded and active) came back `verified` with correct citations.

**Next: graph tools** (build-plan step 10; see [docs/tools.md](docs/tools.md))
- Dedicated tools on top of the graph: ownership lookup, expertise lookup, decision tracing (what
  superseded or contradicted what) and timelines. Today the model has one general `falkordb_query` tool.
- Check the generator against the dataset's traps: superseded decisions, reassignments, a stale strategy
  document, dissent, and a question with a false premise.
- Turn the graph records into richer evidence (a decision's rationale and status, a change's old and new
  value) and carry the current/superseded status through to the response.

**Later:** web API, a configuration file, history and freshness status, incremental updates, evaluation
and proposed actions (steps 8 and 11 to 15).

**Known gaps**
- [x] The model can query the graph: `falkordb_query` returns graph nodes as typed, citable sources.
- [ ] There are no automated tests in the repo yet. The build plan calls for tests against simulated models,
  never a real model service.
- [ ] `falkordb_query` routes natural language to a few fixed query shapes (owners, people involved, list by
  type, keyword search); anything else is a keyword search or raw read-only Cypher.
- [ ] Rows made of columns (for example `RETURN d.key, d.title`) stay generic "Graph result" sources, because
  they are not one node.
- [ ] Ingestion always rebuilds the graph. Incremental updates are a later step.
- [ ] A run on Groq's free tier can take minutes, because of rate-limit waits.
- [ ] The generator sometimes writes "Not in company records: none" instead of leaving the heading out.

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
| `src/tools/` | Tool registry: a function plus a `<name>.json` schema next to it (`get_time`, `falkordb_query`) |
| `src/validations/sources.py` | `Evidence`, `Note`, `Source`, `SourceRegistry`; renders sources as `<source id=...>` blocks |
| `src/validations/citations.py` | Citation syntax: the `[[cite:<id>\|<quote>]]` pattern, quote matching, syntax repair |
| `src/validations/checks.py` | Splits a draft into numbered sentences and finds problems code can prove |
| `src/workflow/tool_loop.py` | `ask(...)`: the bounded model → tools → model loop |
| `src/workflow/reflexion.py` | `run(...)`: the generate → check → fix workflow, plus `Check` and `RunResult` |
| `src/workflow/render.py` | Numbers citations and renders the readable markdown with a source list |
| `src/api/response.py` | `build_response(result)`: the one JSON shape the CLI (and later the API) returns |
| `src/storage/run_logger.py` | Writes each run as JSON plus markdown |
| `src/retrieval/falkordb_client.py` | `FalkorDBClient`: parameterised read-only `query()` returning dict rows, and a separate `write()` used only by ingestion |
| `src/tools/falkordb_query.py` | The graph tool: natural language or read-only Cypher in, one `Evidence` per row out (plus a `Note` when the result is cut off) |
| `schema.py` | Node labels, edge types and which dataset fields become which edges. Ingestion reads most of it; the tool reads the name and date properties |
| `scripts/ingest_company_data.py` | Loads the dataset into FalkorDB: `MERGE` on ids through `UNWIND` with parameters |
| `company_brain_dataset.json` | The synthetic company dataset |
| `docker-compose.yml`, `scripts/db.sh` | FalkorDB with a health check and its browser UI; `db.sh` starts, loads, stops and resets it |
| `src/ingestion/` | Empty. Reserved for the later ingestion work |

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
| `Note` | frozen dataclass (`sources.py`) | `text` | A message about a tool result (e.g. "more rows matched"). The model reads it, but it is never a source, so it can't be cited |
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
  one source holding the whole result. A `Note` in the list is shown to the model after the sources but
  is never registered. Failures never become sources.
- Graph rows: a row that is one node becomes `Evidence` of that node's type (`decision`, `project`, ...),
  titled by its name, title, key or channel, dated from its own date property, and identified by its node
  id. Any other row is a `query_result` identified by a hash of its text.
- A citation's closing `]]` must not be followed by another `]`, so a quote that itself ends in `]` stays
  whole.

### Tool loop (`ask`)

`ask(provider, model, messages, registry, memo=None, user=None, use_tools=True) -> ModelReply`:
- Works on a copy of `messages`; the caller's list is never mutated.
- Each step calls `complete()`. If the model asks for tools, each `ToolCall` runs through `run_tool`,
  registers its result in the registry and appends it as a `tool` message (sources first, then any notes). After `MAX_TOOL_STEPS` the
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
