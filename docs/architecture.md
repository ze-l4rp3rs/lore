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
| Interfaces | Take a question (and optional context text) and return the structured response |
| Provider selection | Picks a model provider from the keys available |
| Answer workflow | Drafts, checks, fix rounds, best-draft choice, logging |
| Tool loop | Runs the bounded "model → tools → model" exchange for one model call |
| Verification | Source registry, quote matching and repair, sentence-level checks |
| Tools | Read the graph and return citable evidence; one tool drafts follow-up actions |
| Graph client | Read-only parameterised queries; a separate write path used only by ingestion |
| Ingestion | Turns datasets, documents and live deltas into graph records |
| Settings | One validated configuration, including all model instructions |
| Run log | A record of every step of every run |

## How a question flows

1. **Entry.** An interface receives the question and optional context, and a provider is chosen.
2. **Registry.** The context is split into sources, each with a random identifier for this run.
3. **Generator.** The model is called with the tool descriptions. Each tool result becomes one or more
   sources and is shown back to the model. This repeats until the model answers or the tool budget
   forces an answer.
4. **Checks.** Citations are repaired, the draft is split into sentences, automatic checks run, and the
   reviewer judges each sentence. The reviewer has no tools, sees the same sources, and sees which tool
   produced which source.
5. **Fix rounds.** If there are problems, the generator's conversation continues with only those
   problems.
6. **Result.** The best draft is kept, unsupported sentences are removed, citations are numbered, a
   readable version is rendered and the run is logged.
7. **Response.** The result is turned into the response structure (see Interfaces).

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
