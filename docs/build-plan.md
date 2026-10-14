# Build plan

Build in this order. Each step ends with a working system and a "done when" check. From step 4 onward,
write automated tests against simulated models; never call a real model service from a test.

---

## Step 1: Question answering over a context file, with one provider

**Build**
- A project skeleton that keeps secrets and generated files out of version control from the start.
- A small sample context of dated records that includes a reassignment and a superseded target date. It
  is the first test of "answer from the latest decision".
- Two model calls: a generator that answers only from the context, and a reviewer that removes
  unsupported claims.
- A command-line entry point that takes a context file and a question.

**Done when** the command line answers a question about the sample, and a missing file gives a clear
error.

---

## Step 2: Tool calling

**Build**
- A tool registry: each tool is a function plus a description of its parameters, discovered
  automatically.
- A first tool that returns the current time.
- A bounded loop: call the model, run the tools it asks for, give it the results, repeat. After a set
  number of tool rounds, the final call must answer without tools.
- Unknown tools, malformed arguments and tools that fail are reported back to the model and never crash
  the run.

**Done when** a simulated model that asks for the time gets the result back, and a call to an unknown
tool is reported rather than crashing.

---

## Step 3: Instructions and the review loop

**Build**
- Generator rules:
  - facts only from sources;
  - answer first, then the support;
  - keep roles apart (owner vs assignee, author vs approver);
  - no preamble;
  - say what is missing.
- A reviewer that returns a structured verdict, read tolerantly even when it has extra text around it.
- Fix rounds: continue the generator's own conversation with only the problems listed, and tell it to
  change nothing else. Limit the number of rounds.
- Removal of any reasoning text the model leaks into its answer. Keep that reasoning in the log instead.

**Done when** a rejected draft is fixed in a second round with its history intact, and leaked reasoning
never reaches the answer.

---

## Step 4: Several model providers

**Build**
- One provider interface: a single "complete this conversation" call that never runs tools itself.
- Adapters for three model providers, each translating the shared conversation format into its own
  (see Architecture).
- Provider selection from the API keys that are set:
  - one key: use it;
  - several keys and a person at a terminal: ask;
  - several keys and nobody to ask: use the configured default;
  - otherwise: fail with a message listing the options.
  Libraries for providers that are not used are never loaded.
- A simulated provider for tests.

**Done when** the same loop works through every adapter, and a server with several keys picks the
default instead of waiting for input.

---

## Step 5: Structured results and run logs

**Build**
- A record of every tool call (name, arguments, result, sources produced, status, error, duration,
  whether it was reused), and reuse of identical tool calls within a run.
- A structured result:
  - answer, readable version and cited sources;
  - removed sentences, unanswered parts and false premises;
  - status and log location;
  - the **measured** number of rounds and elapsed time.
- One log per run with every step in order.

**Done when** a run returns the structured result, and its log shows every draft, review and fix.

---

## Step 6: Sources and citations

**Build**
- A source registry:
  - every piece of evidence the model sees becomes a source with a random identifier for that run;
  - a context file is split into one source per dated record;
  - retrieved text can never imitate the structural markers that separate sources from instructions.
- A citation rule: every fact is followed by a citation that names the source and quotes the exact
  words.
- Rendering: citations become numbered footnotes in order of first use, with a source list.

**Done when** an answer about the sample renders with numbered footnotes and quoted passages.

---

## Step 7: Verification

**Build** (see Answer pipeline)
- Quote matching that forgives letter case, spacing and typographic quote marks, and nothing else.
- Automatic repair of near-miss quotes and malformed citations.
- Sentence-level automatic checks: unknown sources, quotes not in their source, uncited facts, fake
  citations, leaked reasoning.
- A reviewer that judges each numbered sentence and reports unanswered parts and false premises. It
  cannot use tools and sees exactly the evidence the generator saw.
- Best-draft selection, with unsupported sentences removed and listed with a reason.

**Done when** a quote that is one letter off is repaired without another model call, and an invented
sentence is removed and listed.

---

## Step 8: Response format, command line and web API

**Build**
- One builder for the response, shared by the command line and the web API (see Interfaces).
- An HTTP endpoint for questions and one for health. The web API never asks anyone which provider to use.

**Done when** both interfaces return the same response for the same simulated run.

---

## Step 9: Dataset and graph

**Build**
- A synthetic company dataset with deliberate traps:
  - superseded and contradicting decisions;
  - reassignments;
  - a strategy document that later decisions made stale;
  - dissent;
  - a question with a false premise.
- Dataset checks: section counts, and every reference resolves.
- A container setup: a graph database with a health check, plus the agent's API. Keys are supplied at
  run time, never built into an image.
- A graph client that runs read-only parameterised queries and returns named fields, with a separate,
  ingestion-only way to write.
- A single description of the graph model (see Graph schema).
- The ingestion process (see Ingestion).

**Done when** ingestion loads every record, a second run changes nothing, and everything written appears
in the schema description.

---

## Step 10: Graph tools

**Build** (see Tools)
- General graph search, ownership lookup, expertise lookup, decision tracing and timelines.
- Instructions that describe the data model and the tools, and the working order: query first, extract
  facts, cite, then answer.

**Done when** each tool passes tests with a simulated database and works against a real database loaded
with the dataset.

---

## Step 11: Configuration file

**Build**
- Move every setting and every model instruction into one configuration file, loaded once, typed and
  validated (see Configuration).
- Before switching over, prove that every old value and instruction comes through the new loader
  unchanged.

**Done when** no code reads the old settings, and an invalid value fails with a message naming the
setting.

---

## Step 12: History, provenance and freshness

**Build**
- Recorded history (field changes on projects and tickets, and versions of ticket descriptions) stored
  as change records, linked to who made each change, what it changed and what it was based on.
- Decision provenance (the records a decision is based on, overrides, reversals, supersessions), dissent
  with its evidence, document versions, and a "current" flag computed from structure.
- One standard way to turn any graph record into typed, dated evidence with a stable identity.
- A current or superseded status on every source, with a short reason, and conflict rules in the
  instructions.
- Richer tools: a decision's full provenance chain, a change-based timeline with "value on a given date",
  and expertise ranked by evidence.

**Done when** "what was the value on a given date" is computed from recorded changes, and the model sees
a superseded decision labelled as superseded.

---

## Step 13: Incremental updates

**Build**
- Change detection by content fingerprint, an origin on every relationship, a change report, an explicit
  confirmed full rebuild, and optional removal of records missing from the input (see Ingestion).
- A token-protected endpoint for live updates.

**Done when** loading the same data twice reports everything unchanged with no writes, and editing one
record changes exactly one node.

---

## Step 14: Evaluation and actions

**Build**
- Golden questions with checks, an offline check that their expected facts hold in the data, and an
  evaluation runner (see Testing and evaluation).
- A draft-only follow-up tool. Its drafts are returned for a person to confirm and are never sent.

**Done when** the offline fact check passes, and the evaluation runner scores a simulated model
correctly.

---

## Step 15: Bring-up and documentation

**Build**
- A one-command local start: load secrets safely, check prerequisites, start the database, wait until it
  is healthy, and load data if the graph is empty.
- A setup check, and a guide with a quick start, the architecture and a map of the focus areas.

**Done when** a fresh checkout with keys configured goes from the one-command start to a working question
endpoint.
