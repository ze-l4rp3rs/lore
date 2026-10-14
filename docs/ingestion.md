# Ingestion

## Dataset shape

A dataset has:
- one section per entity type (people, teams, projects, tickets, documents, decisions, chat messages),
  each a list of records with an identifier;
- typed relationship lists;
- general metadata, which is never ingested.

## Plan first, then write

Everything is planned before anything is written, so a bad reference fails without changing the graph:

1. **Records:** one per dataset record (properties as in Graph schema), plus change records from history.
2. **Relationships:**
   - from reference fields;
   - from relationship lists (unknown lists are reported and skipped);
   - from provenance: change history, decision evidence, links and dissent, document supersession, and
     names mentioned in chat.
3. **Validation:**
   - every relationship endpoint must exist with the expected type, or the run fails naming the
     offending entry;
   - evidence identifiers that point to nothing are reported, never dropped silently.
4. **Deduplication:** each relationship is written once, with list properties combined. Its origin is
   the first record that produced it.

All writes are batched and parameterised, and failures are never silently ignored. A failing batch is
retried entry by entry, so the error names the entry.

## Incremental update

The default mode:

1. Read what the graph holds: records by type, and every relationship that has an origin.
2. **Records:** compare each record's content fingerprint (taken from the whole source record, minus
   authoring notes) with the stored one. Only added and changed records are written. A write replaces
   all of a record's properties, so stale ones disappear, and updates its "last written" time.
3. **Relationships:** an existing relationship whose origin is a record in this input, but which the
   input no longer implies, is removed (for example the old ownership after an owner change). For
   relationship lists this happens only when the input is a complete dataset.
4. **Change records** that a record's history no longer contains are removed with it.
5. **Current flags** are computed over the graph as it will be after the update, and rewritten only on
   records whose flag actually flips (for example the previous version when a new document version
   arrives).
6. **Report:** added, changed and unchanged per entity type; relationships written and removed; current
   flags updated; records removed.

| Mode | Effect |
|---|---|
| Default | Incremental update. Loading the same data twice reports everything unchanged and writes nothing. |
| Prune | Also removes dataset records missing from the input. Documents loaded from files are never pruned. |
| Full rebuild | Empties the graph and reloads. It requires explicit confirmation. |

## Live updates

The web API accepts a partial update shaped like the dataset, e.g. one new or edited decision:
- it may reference records already in the graph;
- nothing outside the update is removed;
- the response is the change report.

The endpoint is off unless an ingestion token is configured. When it is on, requests must present the
token (compared in constant time), and the body has a size limit.

## Documents from files

A document extraction library turns files (PDF, office formats, Markdown, plain text and more) into text
and metadata:
- each file becomes a document record whose identity comes from its location, so re-loading updates it in
  place;
- files that cannot be extracted are reported and skipped;
- the library is optional, and without it the feature says how to enable it.
