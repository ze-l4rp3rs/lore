# Interfaces

## Command line

- Takes a question, and optionally a context file. The file is split into sources at its dated record
  headers.
- Asks for the question interactively if none is given.
- Prints the structured response.
- With several provider keys set and a person at the terminal, asks which provider to use.

## Web API

| Endpoint | Accepts | Returns |
|---|---|---|
| Health | nothing | an "ok" status |
| Ask | a question and optional context text | the structured response. A missing question or unreadable body is a client error. It never waits for input: with several keys, the configured default provider is used. |
| Live update | a partial dataset | the change report (see Ingestion). Hidden unless an ingestion token is configured. Refused without the token, if too large, or if the data is invalid. Reports when the database is unavailable. |

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
