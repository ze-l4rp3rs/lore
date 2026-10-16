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
  numbered footnotes, is written to `runs/*.md`. It takes `--clearance-level` and `-a/--attachment` too.

The web API runs the same pipeline:

```bash
.venv/bin/python -m src.api.server     # 127.0.0.1:8000 by default
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "Who owns the Platform Redesign project?", "clearance_level": 3}'
```

Every request names a `clearance_level` and may carry attachments, and returns a `metadata.trace` (also
the `X-Request-ID` header) describing the clearance used, what was attached, the provider, the run log
and the time each stage took. Attachments are text inline or raw bytes; raw bytes (a file base64d in the
request) are turned into text by xberg. See [docs/api.md](docs/api.md).

To query the company graph instead of a context file, start FalkorDB, load the dataset, then ask:

```bash
scripts/db.sh up        # FalkorDB on localhost:6379, browser UI on http://localhost:3000
scripts/db.sh ingest company_brain_dataset.json   # or a data/ folder; see "Ingesting data"
python main.py "Who owns the Platform Redesign project?"
scripts/db.sh down      # clean exit (keeps the data); `scripts/db.sh reset` also deletes it
```

- If port 6379 or 3000 is taken, set `FALKORDB_PORT` / `FALKORDB_BROWSER_PORT` (and `FALKORDB_URL` for the
  agent). The ports are bound to `localhost` only, and the image has no password.
- With no context file and no database, the model has nothing to answer from.

### Ingesting data

`scripts/db.sh ingest` (or `python scripts/ingest_company_data.py [source]`) reconciles the graph with a
folder of source files and is safe to run repeatedly against a live database:

```bash
scripts/db.sh ingest                 # reads the data/ folder
scripts/db.sh ingest path/to/data    # or any folder, or a single .json file
python scripts/ingest_company_data.py data --dry-run   # report what would change, write nothing
```

It is **incremental and additive**. Each source file is hashed and remembered in a manifest
(`data/.ingest_manifest.json`) next to the source, together with the node ids that file defined. On the
next run only **added** and **changed** files are written; unchanged files are skipped. A changed file's
edges are replaced with the new ones, and a node id that no longer appears in **any** file is deleted
(with its edges). Nothing else is ever cleared, so it never disturbs unrelated data.

The source folder (`data/` is the default, and is created by you) holds structured `.json` dataset
files and/or company documents (PDF, DOCX, XML, Markdown, plain text, etc.). Company documents are
extracted using xberg into `Document` nodes with their relative path as the node `id` (e.g. `specs/api.xml`),
making them directly citable and connectable.

Structured `.json` files may contain any subset of the sections below; together all files form one dataset.
Node **ids must be unique across the whole folder**, and every id referenced by an edge must be defined
somewhere in the folder. A file may set a `clearance` on any record (see [Clearance](#clearance)); files
and records without one default to the most open level.

```json
{
  "people":    [{"id": "p1", "name": "Dana Okafor", "role": "CTO", "clearance": 3}],
  "teams":     [{"id": "t1", "name": "Platform"}],
  "projects":  [{"id": "pr1", "name": "Platform Redesign", "department": "Platform", "status": "active"}],
  "documents": [{"id": "d1", "title": "Redesign brief", "content": "...", "created": "2026-01-05"}],
  "decisions": [{"id": "dc1", "title": "Adopt Rust", "date": "2026-02-01", "status": "active"}],
  "tickets":   [{"id": "tk1", "title": "Cut SMPP", "project_id": "pr1", "status": "open"}],
  "slack_messages": [{"id": "s1", "text": "...", "channel": "#platform", "user_id": "p1"}],
  "relationships": {
    "owns": [{"person_id": "p1", "project_id": "pr1", "since": "2026-01-01"}]
  }
}
```

- Sections and the fields that become edges are defined in [schema.py](schema.py): `DATASET_SECTIONS` maps
  a section to a node label, and `FIELD_EDGES` / `RELATIONSHIP_SECTIONS` map fields and named edge lists
  to relationships. `company_brain_dataset.json` is a single-file example of the full shape.
- Split a dataset across files however you like (by team, by import, …). An edited file is re-planned as a
  whole, so it is the unit of change.
- The manifest is per source folder; keep it when you move or change data. Add it to version control only
  if you want the incremental state to travel with the folder. Point `FALKORDB_GRAPH_NAME` in `config.py`
  elsewhere if `company_brain` is already in use.

### Clearance

Every node stores a `clearance` (whole number, `0`..`5`; higher is more restricted). Askers pass a
`clearance_level` on every request, and the graph tool returns only nodes at or below that level, so a
low-clearance asker never sees restricted records. The scale, the default and the property name are
defined once in [schema.py](schema.py) and re-exported by `config.py`; records without a `clearance`
default to the most open level.

Provider selection:
- One API key set: that provider is used.
- Several keys and a terminal: you are asked which one.
- Several keys and no terminal: `DEFAULT_PROVIDER` decides (from `.env` or `config.py`).
- No keys: the run fails with a message listing the env vars to set.

## Status & Roadmap

The project follows the 15-step roadmap tracked in [docs/build_steps.md](docs/build_steps.md).
The [docs/](docs/README.md) folder is the single declarative source of truth for all guides and architectural specifications.

For the full breakdown of what is completed and what is coming next, see [docs/build_steps.md](docs/build_steps.md).

**Known gaps**
- [x] The model can query the graph: `falkordb_query` returns graph nodes as typed, citable sources.
- [ ] There are no automated tests in the repo yet. The build plan calls for tests against simulated models,
  never a real model service.
- [ ] `falkordb_query` routes natural language to a few fixed query shapes (owners, people involved, list by
  type, keyword search); anything else is a keyword search or raw read-only Cypher.
- [ ] Rows made of columns (for example `RETURN d.key, d.title`) stay generic "Graph result" sources, because
  they are not one node.
- [ ] Ingestion reconciles by file: editing a large file rewrites all of that file's nodes. Per-record
  change tracking is a later step.
- [ ] Raw Cypher can only be filtered by returned node rows; a raw query that returns bare columns is not
  clearance-filtered. The fixed query shapes always are.
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
| `schema.py` | Node labels, edge types, which dataset fields become which edges, and the clearance scale. Ingestion reads most of it; the tool reads the name, date and clearance constants |
| `scripts/ingest_company_data.py` | Thin CLI over `src/ingestion/sync.py`: reconciles a `data/` folder (or one file) into FalkorDB, incrementally |
| `src/ingestion/sync.py` | The incremental ingester: hashes each source file, plans nodes and edges, writes only what changed, and deletes only node ids no source defines any more |
| `company_brain_dataset.json` | The synthetic company dataset (a single-file example of the `data/` format) |
| `docker-compose.yml`, `scripts/db.sh` | FalkorDB with a health check and its browser UI; `db.sh` starts, loads, stops and resets it |
| `src/ingestion/extractor.py` | `extract_bytes(...)`: turns attachment bytes into text with xberg |

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
