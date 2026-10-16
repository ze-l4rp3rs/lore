# Configuration

All settings and all model instructions live in one configuration file. Secrets never do.

## Settings

| Group | Settings | Default |
|---|---|---|
| Provider choice | default provider, used when several keys are set and nobody can be asked | the first provider |
| Providers | for each provider: the **name** of the environment variable holding its key, the generator model, the reviewer model | one entry per provider |
| Generation | output limit per call | 2000 tokens |
| | temperature | 0 |
| | fix rounds after the first draft | 2 |
| | tool rounds per model call | 6 |
| Verification | quotes required in every citation | yes |
| | similarity needed to repair a misquote | 0.9 |
| | heading for missing information | "Not in company records" |
| Provider-specific | separate reasoning output for reasoning models | on |
| Graph | database location, graph name | a local database (`redis://localhost:6379/0`), `company_brain` |
| Clearance | clearance levels (re-exported from schema.py) | MIN=0, MAX=5 |
| Web API | host, port, debug mode, max attachments, max bytes | 127.0.0.1, 8000, off, 10 files, 10 MB/file, 25 MB total |
| Logs | folder for run logs | `runs/` |
| Instructions | generator, fix request, reviewer | |

## Loading rules

- **Loading:** read once, cached, and returned as read-only typed values.
- **Location:** an environment variable can point at a different configuration file.
- **Errors name the setting,** e.g. "generation output limit must be a positive whole number".
- **Environment overrides:** database location, default provider, API host/port/debug.
- **Instruction placeholders:** the missing-information heading is inserted with plain text replacement,
  never a templating step, because the reviewer's instructions contain literal structured-data examples.
  The fix request keeps a placeholder for the problem list.
- **Secrets:** a provider entry that looks like it holds a secret is rejected. Keys live only in the
  environment.

## Environment

| Setting | Purpose |
|---|---|
| One API key per provider (`GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) | Decides which providers are available |
| `DEFAULT_PROVIDER` | Overrides the configured default provider |
| `FALKORDB_URL`, `FALKORDB_GRAPH_NAME` | Overrides the configured database location and graph name |
| `API_HOST`, `API_PORT`, `API_DEBUG` | Overrides web API server host, port and debug reload |
| `INGESTION_TOKEN` | Enables live updates (when implemented); unset means the endpoint is off |

The example environment template lists only settings the system actually reads.
