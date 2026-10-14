# Testing and evaluation

## Rules

- **No test calls a real model or needs a database.** Everything is simulated.
- **Every test runs isolated:**
  - in a temporary folder;
  - with no API keys or configuration overrides from the environment;
  - never reading a developer's secrets file;
  - with fresh settings.
- **A test can change settings** for its own duration only.

## Simulations

| Simulation | Use |
|---|---|
| Scripted model | Returns queued replies and records each request |
| Citing model | End to end: the generator cites real source identifiers it was shown; the reviewer approves every sentence |
| Recording graph client | For tools: records each query and its parameters, answers with prepared rows |
| In-memory graph | Understands the ingestion reads and writes, so updates, removals and reports can be checked |
| Simulated provider services | Canned responses for each provider adapter |

## What to test at each layer

- **Adapters:** conversation conversion, retries, output-cap reduction, tool-choice mapping.
- **Tool loop:** results shown back to the model, the forced final answer, unknown tools, reuse of
  repeated calls, removal of leaked reasoning.
- **Verification:**
  - quote-matching edge cases and the repair threshold;
  - each sentence check;
  - a full run where a misquote is repaired and an invented sentence is dropped.
- **Graph tools:**
  - queries are parameterised and never contain user text;
  - evidence text and references are right;
  - failures fail.
- **Ingestion:**
  - counts derived independently from the dataset;
  - every type written appears in the schema description;
  - authoring notes are never stored;
  - loading twice changes nothing, and editing one record changes exactly one.
- **Interfaces:** the command line and the web API return the expected response structure.

## Automated check

Run before any change is accepted:
1. Everything compiles, with no undefined names.
2. Every module loads.
3. A simulated run through each interface, confirming that a misquote is repaired.
4. The full test suite.
5. Container and start-up configuration are valid, and every path they mention exists.
6. No company-specific names appear in the logic, schema, instructions or configuration.
7. No secrets or generated files are tracked.

## Golden questions

Each golden question has:
- an identifier;
- the focus areas it exercises;
- the question;
- an optional context file;
- checks on the answer:
  - phrases that must appear (patterns, ignoring case and citation markers);
  - phrases that must or must not appear in the first sentence;
  - a false premise that must be corrected;
  - a gap that must be stated;
  - records that must be cited.

Each question also lists the facts its checks rely on. An offline fact check confirms every one of them
against the dataset and context files, and runs with the test suite. It knows only general kinds of fact,
so it stays company-agnostic:
- a field's value;
- the latest change and the value on a date;
- dissent;
- a message that exists;
- a document dated after a decision;
- evidence lists;
- people computed from a decision;
- absence of an amount;
- context text;
- blocked items and their owners.

**When a fact fails,** fix the golden question, not the data.

**What to cover**
- current owners and current values;
- a value on a past date;
- provenance trails;
- a superseded document;
- a false premise;
- a figure that does not exist;
- a question about a context file.

## Evaluation runner

- Runs every golden question (or a chosen subset) through the agent with a chosen provider.
- Prints a pass/fail table with the failed checks and a score per focus area.
- Fails below a chosen threshold.
- Needs real API keys and a loaded graph.
- Scores are reported, never stored with the project.
