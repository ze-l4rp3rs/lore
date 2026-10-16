# Operations

## Local bring-up

One command brings the system up locally:
1. **Secrets.** Loads them from the local secrets file so that values with spaces or quotes survive.
2. **Prerequisites.** Checks the language runtime version and the container tools, using whichever
   compose command is available.
3. **Setup check.** Confirms the configuration loads and at least one provider key is set.
4. **Database.** Starts it and waits for its **health check** to pass (no fixed waits), then confirms the
   agent can reach it.
5. **Data.** Loads the sample dataset if the graph is empty, then lists what to do next.

## Containers

**Database container**
- Uses the official graph database image.
- Keeps its data on a persistent volume.
- Has a health check.

**Agent container**
- Starts only once the database is healthy, and serves the web API.
- Receives provider keys, the default provider and the ingestion token from the environment at run time.
- Writes run logs to the host.
- Reads the configuration from the host, read-only, so settings change without rebuilding.

**Agent image**
- Copies the files it needs **one by one**, never the whole project, so a local secrets file can never
  be included.
- Contains no API keys.

Ingestion can also run inside the agent container.

## Security

- **Secrets** live only in the environment. Configuration names them but never holds them.
- **Clearance and data isolation:** every query is constrained by the caller's clearance level (0 to 5);
  lower-clearance askers never receive restricted nodes or relationships. Raw Cypher results are post-filtered.
- **Attachment safety:** incoming request attachments are checked against count and byte size limits
  (10 files max, 10 MB per file, 25 MB total) before extraction.
- **The model cannot change the graph:**
  - tool queries are read-only;
  - model-written queries are screened for anything that writes, and run read-only regardless;
  - user and model text is always passed as a parameter, never pasted into a query.
- **Retrieved text cannot fake structure:** it cannot close the markers that separate sources from
  instructions, and it cannot forge citation identifiers, which are random for each run.
- **Live updates** are off by default. When on, they need a token compared in constant time, are capped
  in size, and validate data before writing anything.
- **Drafted follow-ups are never sent;** a person confirms them.
- **Authoring notes are never ingested.**

## Logs

Every run produces a structured log of every step: drafts, tool calls with timings and reuse flags,
reviews, fix requests and errors. It also produces a readable copy of the final answer. Use the logs to
debug instructions and tool behaviour.
