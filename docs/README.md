# Company Brain: design and build guide

Company Brain is an agent that understands how a company works. People, teams, projects, tickets,
documents, decisions, chat messages and recorded changes live in one graph. The agent answers questions
from that graph, and every fact in an answer carries a quote from a specific record.

These documents describe the system well enough to build it again from nothing.

## Reading order & Guides

The `docs/` folder is the single declarative source of truth for all architecture and design decisions:

| Document | File | What it covers |
|---|---|---|
| Build steps | [build_steps.md](build_steps.md) | Progress tracker and roadmap with checkboxes for all 15 build steps |
| Architecture | [architecture.md](architecture.md) | Components, service pipeline, how a question flows, core concepts |
| Graph schema | [schema.md](schema.md) | Entity types, node properties, relationship types, and clearance rules |
| Answer pipeline | [answer-pipeline.md](answer-pipeline.md) | Generator, citations, automatic code checks, reviewer, fix rounds |
| Tools | [tools.md](tools.md) | Available tools, Cypher query planning, clearance filtering, citable evidence |
| Ingestion | [ingestion.md](ingestion.md) | Multi-format document ingestion (PDF, XML, MD, etc.), folder reconciliation |
| Interfaces | [api.md](api.md) | Command line and FastAPI Web API request/response schemas, trace headers |
| Configuration | [configuration.md](configuration.md) | System settings, loading rules, environment variable overrides |
| Testing and evaluation | [testing-and-eval.md](testing-and-eval.md) | Testing rules, fakes, simulated models, and golden questions |
| Operations | [operations.md](operations.md) | Containers, local bring-up, clearance security, execution logs |

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
