# Company Brain: design and build guide

Company Brain is an agent that understands how a company works. People, teams, projects, tickets,
documents, decisions, chat messages and recorded changes live in one graph. The agent answers questions
from that graph, and every fact in an answer carries a quote from a specific record.

These documents describe the system well enough to build it again from nothing.

## Reading order

| Document | What it covers |
|---|---|
| Build plan | The order to build things in, with a "done when" test for each step |
| Architecture | Components, how a question flows through them, the core concepts |
| Graph schema | Entity types, properties, relationships, derived data, what is never stored |
| Answer pipeline | Generator, citations, automatic checks, reviewer, fix rounds, best draft |
| Tools | What each tool does, how tool results become citable sources, how to add a tool |
| Ingestion | Loading a dataset, incremental updates, change reports, live updates, documents from files |
| Interfaces | Command line, HTTP endpoints and the structure of a response |
| Configuration | The settings, how they are loaded and validated, how secrets are handled |
| Testing and evaluation | Fakes, the automated checks, golden questions, the evaluation runner |
| Operations | Containers, local bring-up, security, logs |

## What it must do

1. Put docs, tickets and chats in one graph.
2. Answer who owns what and who knows what.
3. Trace decisions back to their sources.
4. Keep knowledge current as things change.
5. Give answers with clear sources.

## Principles

- **Every fact is cited with an exact quote.** Automatic checks verify the quote against the source. A
  model only judges what those checks cannot.
- **Errors are never sources.** A failing tool reports a failure; it never returns an error message the
  model could cite as fact.
- **Structure decides freshness; the model decides meaning.** The graph marks what has been replaced.
  The model decides whether a document is out of date compared with recorded changes.
- **Generic by design.** No company, person or record identifier is built into the logic, the schema or
  the instructions given to the model; such details live only in data, tests and evaluation material.
- **Every step leaves a working system.** Each stage runs end to end against simulated models before the
  next begins.
