# Graph schema

One description of the graph model drives both ingestion and the tools. Entity types, relationship types
and property names are defined once, so the documentation and the behaviour cannot drift apart.

## Entity types

| Entity | Source | Main properties |
|---|---|---|
| Person | people | identifier, name, email, role, department, start date, manager, team |
| Team | teams | identifier, name |
| Project | projects | identifier, name, department, status, priority, scope, budget, target end date |
| Ticket | tickets | identifier, key, title, status, priority, created / resolved / due dates, description, comments |
| Document | documents | identifier, title, family, version, created date, status, content, key facts, **current flag** |
| Decision | decisions | identifier, key, title, date, status, description, rationale, impact, details, **current flag** |
| Chat message | chat messages | identifier, channel, author name, timestamp, text, thread, reactions |
| Change | derived from history | identifier, entity and entity type, field, old and new value, date, reason, version, sequence, **current flag** |

Every ingested record also carries a content fingerprint and the time it was last written.

**Property rules**
- Simple values and lists of simple values are stored as they are.
- Nested structures are stored as text.
- Empty values are skipped.
- Documents loaded from files also carry author name, format, source location and tags, and get an
  identity derived from their location.

## Relationship types

Direction matters: a newer record points at the older one it replaces.

| Relationship | Between | Comes from |
|---|---|---|
| OWNS | person → project | the project's owner |
| SPONSORS | person → project | the project's sponsor |
| LEADS | person → team | the team's lead |
| MEMBER_OF | person → team | the team's members |
| APPROVED | person → decision | the decision's approver |
| AUTHORED_BY | document → person | the document's author |
| ASSIGNED_TO | ticket → person | the ticket's assignee |
| REPORTED_BY | ticket → person | the ticket's reporter |
| POSTED | person → chat message | the message's author |
| MENTIONS | chat message → project, ticket or person | relationship lists; names mentioned in the message |
| BELONGS_TO | ticket → project | relationship list |
| BLOCKS, SPLIT_FROM, RELATED_TO | ticket → ticket | relationship lists; a split carries its date and evidence |
| CONTRADICTS | decision → decision | relationship list |
| SUPERSEDES | newer decision or document → older | relationship lists; a document's "supersedes" field |
| SUPERSEDED_BY | older decision → newer | the decision's field, only when no SUPERSEDES relationship already records it |
| OVERRIDES, REVERSES | decision → decision | the decision's fields |
| AFFECTS | decision → project | relationship list |
| DOCUMENTED_IN, ANNOUNCED_IN | decision → document or chat message | relationship lists |
| TRIGGERED | document → decision | relationship list |
| DISSENTS | person → decision | relationship list and the decision's dissent; carries the combined evidence |
| MADE_CHANGE | person → change | who made the change |
| CHANGES | change → project or ticket | the record whose history it is |
| SOURCED_FROM | change or decision → document, chat message or decision | the record's evidence lists |

Every ingested relationship records its origin: the record, or the relationship list, it was read from.

## Derived data

**Change identity** is stable and based on position: the owning record, the kind of history, and the
entry's position or version.

**The current flag** is computed from structure only:
- **Document:** not current if another document supersedes it or its family has a later version.
- **Decision:** not current if it is superseded or reversed, or its status says superseded.
- **Change:** current only if it is the latest recorded change to that field of that entity.

**Source status** is "current" or "superseded", taken from the current flag, with a short reason.

## Never stored

- **Authoring commentary:** notes on records and relationship rows, and notes on the dataset itself.
  These can contain the answer key.
- **Fields that became relationships:** owners, members, evidence lists, dissent, mentions, supersession
  and override fields.
- **Nested history:** it becomes change records instead.

## Making it generic

A new company's data needs only three mappings:
- its sections to entity types;
- its reference fields to relationships;
- its relationship lists to relationship types.

No tool assumes a particular company, person or identifier. Name-like and date-like properties are tried
in a fixed order.
