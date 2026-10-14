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
| Graph | database location, graph name | a local database |
| Web API | host, port, debug mode, maximum live-update size | all interfaces, a standard port, off, 1 MB |
| Logs | folder for run logs | a local folder |
| Instructions | generator, fix request, reviewer | |

## Loading rules

- **Loading:** read once, cached, and returned as read-only typed values.
- **Location:** an environment variable can point at a different configuration file.
- **Errors name the setting,** e.g. "generation output limit must be a positive whole number".
- **Environment overrides:** only the database location and the default provider.
- **Instruction placeholders:** the missing-information heading is inserted with plain text replacement,
  never a templating step, because the reviewer's instructions contain literal structured-data examples.
  The fix request keeps a placeholder for the problem list.
- **Secrets:** a provider entry that looks like it holds a secret is rejected. Keys live only in the
  environment.

## Environment

| Setting | Purpose |
|---|---|
| One API key per provider | Decides which providers are available |
| Default provider | Overrides the configured default |
| Database location | Overrides the configured location |
| Ingestion token | Enables live updates; unset means the endpoint is off |
| Configuration location | Points at a different configuration file |

The example environment template lists only settings the system actually reads.
