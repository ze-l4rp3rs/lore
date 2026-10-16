# Architecture

## Components

```
              ┌──────────────┐     ┌──────────────┐
  question ──►│ Command line │     │ Web API      │◄── questions, live updates
              └──────┬───────┘     └──────┬───────┘
                     └──────────┬─────────┘
                                ▼
                     ┌─────────────────────┐   chosen by provider selection
                     │ Answer workflow     │──────────────────────────────┐
                     └──┬───────────┬──────┘                              ▼
                        │           │                        ┌────────────────────────┐
                        ▼           ▼                        │ Model provider adapters│
              ┌──────────────┐ ┌──────────────┐              └────────────────────────┘
              │ Tool loop    │ │ Verification │
              └──────┬───────┘ │ (sources,    │
                     ▼         │  citations,  │
              ┌──────────────┐ │  checks)     │
              │ Tools        │ └──────────────┘
              └──────┬───────┘
                     ▼
              Graph client ──► Graph database ◄── Ingestion (dataset files, documents, live deltas)
```

| Component | Responsibility |
|---|---|
| Interfaces | CLI (`main.py`) and FastAPI server (`src/api/server.py`) accepting questions, clearance and attachments |
| Service pipeline | `src/api/service.py`: extracts attachments, combines context, handles clearance, orchestrates workflow |
| Provider selection | Picks a model provider from the keys available |
| Answer workflow | Drafts, checks, fix rounds, best-draft choice, logging (`src/workflow/reflexion.py`) |
| Tool loop | Runs the bounded "model → tools → model" exchange for one model call |
| Verification | Source registry, quote matching and repair, sentence-level checks |
| Tools | Read the graph and return citable evidence, filtered by the caller's clearance level |
| Graph client | Read-only parameterised queries; a separate write path used only by ingestion |
| Ingestion | Incremental reconciliation of data files, document extraction via xberg |
| Settings | One validated configuration, including all model instructions |
| Run log | A record of every step of every run |

## How a question flows

1. **Entry & Attachments.** An interface receives the question, clearance level, optional context text,
   and file attachments. The service pipeline resolves attachments (plain text inline; raw binary bytes
   extracted into text and metadata via xberg).
2. **Context & Registry.** Context text and resolved file attachments are combined with record headers
   (`[context: ...]` / `[file: ...]`) into the source registry, each with a random identifier for this run.
3. **Generator & Tools.** The model is called with tool schemas. Tool calls receive the caller's clearance
   level and return only matching graph records. Each result becomes one or more citable sources.
4. **Checks.** Citations are repaired, the draft is split into sentences, automatic checks run, and the
   reviewer judges each sentence. The reviewer has no tools, sees the same sources, and sees which tool
   produced which source.
5. **Fix rounds.** If there are problems, the generator's conversation continues with only those
   problems.
6. **Result.** The best draft is kept, unsupported sentences are removed, citations are numbered, a
   readable version is rendered and the run is logged.
7. **Response.** The result is turned into the response structure (see Interfaces), and API requests
   attach a performance trace (`metadata.trace`).

## Core concepts

| Concept | Meaning |
|---|---|
| Message history | One provider-neutral conversation format shared by all adapters, including tool requests and tool results |
| Completion | One model reply: text, tool requests, finish reason, separately returned reasoning |
| Provider | A name, a "complete" call, and the models used for generating and reviewing |
| Evidence | What a tool returns: kind, label, text, date, link, stable reference, metadata, freshness status and note |
| Source | Evidence registered for a run, with the random identifier the model cites |
| Tool trace | A record of one tool call: arguments, result, sources produced, status, error, duration, reuse |
| Run result | Answer, readable version, sources, removed sentences, unanswered parts, false premises, status, rounds, duration, proposed actions |

## Provider adapters

Every adapter takes the same conversation and makes exactly one service call; running tools stays in the
loop.

| Provider | Differences the adapter handles |
|---|---|
| Fast open-model host | Retries short rate limits. When a request exceeds a per-minute output cap, it lowers the output limit and remembers it. Asks the service to return reasoning separately. |
| Anthropic | Instructions go in a separate field. Tool requests and results are content blocks. Roles must strictly alternate, so consecutive turns from the same side are merged. |
| Google | The assistant role has a different name. A replayed tool request must carry the signature it was issued with. Request identifiers are sent back only if the service created them. Tools without parameters omit the parameter description. |

## Design choices

- **Generator and reviewer share one source registry,** so the reviewer judges exactly the evidence the
  generator saw.
- **Source identifiers are random for each run,** so retrieved text cannot forge a citation.
- **Evidence references are stable graph identities,** so a record returned twice is one source.
- **The reviewer cannot use tools,** so it stays independent of the generator.
- **Settings are read when needed through a cached loader,** so tests can override them.
