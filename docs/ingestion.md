# Ingestion

## Data shape

The sources live in a folder (`data/` by default), which can hold:
- **Structured dataset files (`.json`):** containing zero or more sections per entity type (people, teams,
  projects, tickets, documents, decisions, chat messages) and optional named relationship lists.
- **Actual company documents (PDF, DOCX, XML, Markdown, plain text, etc.):** extracted using xberg into
  `Document` nodes. Each document node's `id` is its relative path inside the folder (e.g.
  `policies/security.pdf`), allowing structured entities in `.json` files to link directly to it (e.g.
  via `DECISION_DOCUMENTED_IN` or `DOCUMENT_SUPERSEDES_DOCUMENT`).

The sections and the fields that become edges are defined in [schema.py](../schema.py)
(`DATASET_SECTIONS`, `FIELD_EDGES`, `RELATIONSHIP_SECTIONS`). Node **ids are unique across the whole
folder**, and every id an edge references must be defined somewhere in the folder. Any record may carry a
`clearance` (0 to 5, defaulting to the most open level); see the README "Clearance" section.
`company_brain_dataset.json` is a single-file example of the full JSON shape.

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
4. **Deduplication:** each relationship is written once. Its origin is the first source file that
   produced it.

All writes are batched and parameterised, and failures are never silently ignored. A failing batch is
retried entry by entry, so the error names the entry.

## Incremental update

Ingestion is incremental and additive by default, and safe against a live database. State lives in a
manifest (`.ingest_manifest.json`) next to the source folder:

1. **Hashing:** every source file is content-hashed. Files are classified against the manifest as added,
   changed, removed or unchanged.
2. **Plan:** all files are planned together (records and relationships) and validated as one dataset, so
   cross-file references are checked before anything is written.
3. **Removals first:** a node id that appeared in the manifest but no longer appears in any file is
   deleted (`DETACH DELETE` by id). The graph is never cleared.
4. **Edges:** every edge owned by a changed or removed file (`r.origin`) is deleted; added and changed
   files then write their current nodes (`MERGE` on id, `SET n = row`) and edges (`MERGE` + `SET r`).
   Unchanged files are skipped entirely.
5. **Manifest:** each written file's hash and the node ids it defines are recorded.

| Run | Effect |
|---|---|
| Default | Incremental reconcile. Loading the same sources twice reports everything unchanged and writes nothing. |
| `--dry-run` | Report what would change; write nothing. |

Nothing outside the sources is ever removed. A production graph can hold records that the sources do not
describe; they are left alone. There is no full-rebuild mode: to start over, reset the database
(`scripts/db.sh reset`).

A file is the unit of change: editing one record re-writes that file's nodes. Per-record change tracking
is a later step.

## Live updates

A live update endpoint (partial dataset in, change report out) is a later step; only the offline script
exists today.

## Documents from files

xberg ([pypi](https://pypi.org/project/xberg/)) turns files (PDF, office formats, Markdown, plain text
and more) into text and metadata. `src/ingestion/extractor.py` is the one seam: it takes file bytes plus
the file's name and content type and returns the text and metadata, or raises `ExtractionError`.
Request attachments use it today (see Interfaces); ingestion of documents from files uses the same call.
- each file becomes a document record whose identity comes from its location, so re-loading updates it in
  place;
- files that cannot be extracted are reported and skipped;
- the library is optional at runtime: if it is not installed the extractor raises `ExtractionUnavailable`
  ("run: pip install xberg") and callers report it instead of failing.
