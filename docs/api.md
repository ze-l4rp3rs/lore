# Interfaces

## Command line

- Takes a question, and optionally a context file (`-c/--context`). The file is split into sources at its
  dated record headers.
- Asks for the question interactively if none is given.
- Accepts `--clearance-level` (whole number 0 to 5, default 5 on CLI).
- Accepts `-a/--attachment PATH` (repeatable) to attach local text or binary files.
- Prints the structured response.
- With several provider keys set and a person at the terminal, asks which provider to use.

## Web API

| Endpoint | Accepts | Returns |
|---|---|---|
| Health (`GET /health`) | nothing | `{"status": "ok"}` |
| Ask (`POST /ask`) | JSON payload (`question`, `clearance_level`, `context`, `attachments`) | the structured response, plus a per-request trace (`metadata.trace` and `X-Request-ID` header). A missing question, out-of-range clearance, or invalid attachment is a 4xx error. It never waits for input: with several keys, the configured default provider is used. |
| Live update | a partial dataset | *Planned for a later step.* The offline sync script (`scripts/ingest_company_data.py`) reconciles the graph today. |

### Ask request schema

```json
{
  "question": "Who owns the Platform Redesign project?",
  "clearance_level": 3,
  "context": "optional context text",
  "attachments": [
    {"filename": "notes.txt", "text": "inline notes content"},
    {"filename": "spec.pdf", "data_base64": "JVBERi0xLjQK...", "content_type": "application/pdf"}
  ]
}
```

- `question`: required non-empty string.
- `clearance_level`: integer between 0 and 5, defaulting to 0 (least privilege / most open).
- `context`: optional text string.
- `attachments`: list of up to 10 files (max 10 MB per file, max 25 MB total). Each item requires a
  `filename` and exactly one of `text` (inline text) or `data_base64` (base64-encoded bytes, extracted by
  xberg). Optional `content_type`.

The asker is identified by a clearance level alone (0 to 5, higher is more restricted); the server never
carries a user id. Graph records are returned only at or below that level. Both CLI and Web API run
through the shared service pipeline (`src/api/service.py`).

## Response structure

One builder produces the response for both interfaces. Later versions only add parts.

| Part | Contents |
|---|---|
| Answer | The answer text with a marker after each cited fact, pointing at a reference. Render markers inline or as footnotes. |
| References | One per cited source: identifier, footnote number, type, title, first quote, all quotes, date, link (empty when none), graph identity (or "type:label" for sources outside the graph), metadata, and freshness status (current, superseded or unknown) |
| Status | verified, partly verified, or not checked |
| Unverified | Sentences that were removed, each with a plain-language reason |
| Missing | Parts of the question the records do not answer |
| Premise | False assumptions in the question |
| Proposed actions | Drafted follow-ups (kind, recipient, subject, body, justifying sources), all awaiting a person's confirmation |
| Metadata | Number of rounds, whether the answer was fully verified, and processing time, all measured from the run |
