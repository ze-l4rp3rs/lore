# Build Steps & Progress Tracker

This document is the roadmap for Company Brain (Lore). It tracks what has been built and what comes next across the 15 planned steps.

## Status Summary

| Step | Focus Area | Status | Key Deliverable |
|:---|:---|:---:|:---|
| [Step 1](#step-1-question-answering-over-a-context-file-with-one-provider) | Core Q&A | `[x] Done` | Context file question answering with generator and reviewer |
| [Step 2](#step-2-tool-calling) | Tool Calling | `[x] Done` | Bounded model-tool execution loop and error isolation |
| [Step 3](#step-3-instructions-and-the-review-loop) | Review Loop | `[x] Done` | Fact-checking reviewer, fix rounds, leaked reasoning stripped |
| [Step 4](#step-4-several-model-providers) | Providers | `[x] Done` | Adapters for Groq, Anthropic, and Gemini |
| [Step 5](#step-5-structured-results-and-run-logs) | Logging | `[x] Done` | Per-run structured JSON and markdown execution logs |
| [Step 6](#step-6-sources-and-citations) | Sources & Citations | `[x] Done` | Random per-run source IDs, numbered footnote rendering |
| [Step 7](#step-7-verification) | Verification | `[x] Done` | Automatic quote matching, syntax repair, sentence-level checks |
| [Step 8](#step-8-response-format-command-line-and-web-api) | Interfaces | `[x] Done` | Unified CLI (`main.py`) and FastAPI Web API (`src/api/server.py`) |
| [Step 9](#step-9-dataset-and-graph) | Database & Graph | `[x] Done` | FalkorDB integration, schema definitions, reference dataset |
| [Step 10](#step-10-graph-tools) | Graph Tools | `[x] Done` | `falkordb_query` with query planning and clearance filtering |
| [Step 11](#step-11-configuration-file) | Configuration | `[ ] Next` | Consolidated typed configuration loader |
| [Step 12](#step-12-history-provenance-and-freshness) | Freshness & Provenance | `[ ] Next` | Change records, decision provenance chains, superseded tracking |
| [Step 13](#step-13-incremental-updates) | Incremental Ingestion | `[x] Done` | Manifest hashing, multi-format file extraction (PDF, XML, etc.) |
| [Step 14](#step-14-evaluation-and-actions) | Evaluation & Actions | `[ ] Next` | Golden questions evaluation runner, draft follow-up actions tool |
| [Step 15](#step-15-bring-up-and-documentation) | Bring-up & Ops | `[ ] Next` | One-command start script and setup doctor |

---

## Step 1: Question answering over a context file, with one provider
- [x] Project skeleton keeping secrets and generated files out of version control.
- [x] Context file parsing with dated record headers (`[kind: label, date]`).
- [x] Generator answering only from provided sources.
- [x] Reviewer validating and dropping unsupported sentences.
- [x] CLI entry point accepting a context file and a question.

**Done when:** The CLI answers questions about a context file and provides a clear error on missing files.

---

## Step 2: Tool calling
- [x] Automatic tool discovery with function schemas (`TOOL_SCHEMAS`).
- [x] `get_time` tool providing the current timestamp.
- [x] Bounded execution loop in `src/workflow/tool_loop.py` enforcing `MAX_TOOL_STEPS`.
- [x] Tool failures and bad arguments reported back to the model without crashing.

**Done when:** Tool execution runs within a bounded loop, unknown tools are caught safely, and the model forced to answer once budget is exhausted.

---

## Step 3: Instructions and the review loop
- [x] Core generator instructions enforcing fact extraction before answering.
- [x] Structured JSON reviewer output parsed tolerantly.
- [x] Fix rounds continuing the generator conversation with only identified problems.
- [x] Stripping leaked reasoning blocks (`<think>...`) from answers into logs.

**Done when:** Rejected drafts are repaired in targeted fix rounds and leaked reasoning never appears in final answers.

---

## Step 4: Several model providers
- [x] Unified provider-neutral conversation format (`Message`, `Completion`).
- [x] Adapters for Groq, Anthropic, and Gemini in `src/providers/`.
- [x] Provider selection based on available environment keys, with interactive prompt or default.

**Done when:** The answer loop runs through any configured provider without modifying core pipeline code.

---

## Step 5: Structured results and run logs
- [x] Tool trace recording names, arguments, timings, errors, and reuse.
- [x] Structured `RunResult` dataclass holding answers, sources, unverified claims, and elapsed time.
- [x] Run logger writing full run JSON and human-readable markdown to `runs/`.

**Done when:** Each run outputs a structured response and persists a full execution log.

---

## Step 6: Sources and citations
- [x] `SourceRegistry` generating random per-run IDs to prevent citation forgery.
- [x] Token citation syntax: `[[cite:<id>|<exact quote>]]`.
- [x] Rendering pipeline converting tokens into numbered footnotes and bibliography.

**Done when:** Answers produce numbered footnotes with exact quotes verified against source text.

---

## Step 7: Verification
- [x] Quote matching forgiving whitespace, case, and typographic punctuation.
- [x] Automatic deterministic repair for bracket syntax and separators.
- [x] Sentence-level checks flagging missing quotes, uncited claims, or fake citations.
- [x] Reflector judging factual accuracy without tool access.
- [x] Best-draft selection keeping the cleanest revision.

**Done when:** Near-miss citations are automatically repaired without extra model calls, and unbacked claims are excised.

---

## Step 8: Response format, command line and web API
- [x] Unified response builder (`src/api/response.py`) for both CLI and API.
- [x] FastAPI web server (`src/api/server.py`) with `/health` and `/ask` endpoints.
- [x] Per-request execution tracing (`X-Request-ID` and `metadata.trace`).
- [x] Shared service pipeline (`src/api/service.py`) supporting file attachments.

**Done when:** Both the CLI and Web API run through the same core pipeline and return identical response structures.

---

## Step 9: Dataset and graph
- [x] Synthetic 144-node "Meridian" reference dataset (`company_brain_dataset.json`).
- [x] Entity, relationship, and property definitions in `schema.py`.
- [x] Read-only parameterised FalkorDB client with dedicated write path for ingestion.
- [x] Docker Compose setup (`docker-compose.yml`, `scripts/db.sh`).

**Done when:** The company graph loads cleanly into FalkorDB and conforms to the defined schema.

---

## Step 10: Graph tools
- [x] `falkordb_query` tool supporting natural language and read-only Cypher.
- [x] Read-only query screening blocking Cypher write clauses.
- [x] Clearance filtering: template queries inject clearance constraints; raw Cypher post-filters rows.
- [x] Query result rows mapped to typed, citable `Evidence` sources.

**Done when:** Graph queries return typed sources filtered by the caller's clearance level.

---

## Step 11: Configuration file
- [ ] Move all scattered settings and prompt strings into a unified configuration module.
- [ ] Typed validation for all configuration keys on startup.
- [ ] Dedicated prompt files (`.txt` or `.md`) separated from Python string constants.

**Done when:** All configuration and prompt strings load through a single typed validation interface.

---

## Step 12: History, provenance and freshness
- [ ] Field change history on projects and tickets stored as change records.
- [ ] Decision provenance chains tracking overrides, reversals, and supersessions.
- [ ] "Current" vs "superseded" freshness indicators on sources.
- [ ] Provenance-aware query tools (e.g. timelines, historical values on dates).

**Done when:** The model detects superseded records and explains when a decision or document has been replaced.

---

## Step 13: Incremental updates
- [x] Content hashing (SHA-256) per source file tracked in `.ingest_manifest.json`.
- [x] Multi-format file ingestion supporting PDF, DOCX, XML, Markdown, and text via xberg.
- [x] Non-destructive reconcile: only added and changed files are written; deleted file nodes removed.
- [x] Cross-file reference resolution across dataset files and document files in `data/`.
- [ ] Live partial-update HTTP endpoint protected by an ingestion token.

**Done when:** Re-running ingestion on an unchanged folder performs zero database writes, and actual company documents (PDF/XML/MD) ingest seamlessly into the graph.

---

## Step 14: Evaluation and actions
- [ ] Golden questions suite testing factual accuracy, false premise detection, and gaps.
- [ ] Automated offline fact-checking test runner.
- [ ] Draft follow-up action tool producing confirmed-only external actions.

**Done when:** The evaluation test suite scores simulated models against golden questions automatically.

---

## Step 15: Bring-up and documentation
- [ ] One-command local setup verifying runtime prerequisites, starting database, and checking health.
- [ ] Unified documentation index in `docs/` pointing to all subsystem guides.
- [ ] Diagnostic doctor command checking environment keys and database connectivity.

**Done when:** A fresh checkout brings up the full system with a single command and passes all health checks.
