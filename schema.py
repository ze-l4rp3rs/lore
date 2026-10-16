# schema.py
"""Generic schema configuration for Company Brain.

Defines entity types, relationships, and property mappings
to support any company structure without hard-coding.

Who reads what:
- src/ingestion/sync.py (used by scripts/ingest_company_data.py): ENTITY_TYPES, DATASET_SECTIONS,
  FIELD_EDGES, RELATIONSHIP_SECTIONS, EXCLUDED_FIELDS, and the CLEARANCE_* constants. Every node label,
  edge type and clearance rule it writes is listed here.
- src/tools/falkordb_query.py: NAME_PROPERTIES (a node's display name) and the CLEARANCE_* constants (it
  returns only nodes at or below the asker's level). ENTITY_TYPES and DATE_PROPERTIES are for the graph
  tools still to come (ownership, expertise, decision tracing, timelines).
- documentation only: RELATIONSHIP_TYPES descriptions, PROPERTY_ALIASES, NODE_PROPERTIES,
  CONFLICT_EDGES, SOURCE_AUTHORITY.
"""

# Clearance levels. Every node carries one, so the graph can be served to askers at different
# trust levels: a tool returns only nodes whose clearance is at or below the asker's level.
# Records that do not set one get DEFAULT_CLEARANCE_LEVEL. The scale is whole numbers, higher = more
# restricted. This is the single definition; config.py and the API read these constants.
CLEARANCE_PROPERTY = "clearance"
MIN_CLEARANCE_LEVEL = 0
MAX_CLEARANCE_LEVEL = 5
DEFAULT_CLEARANCE_LEVEL = 0  # most open; what a record without an explicit level is treated as

# Entity types that can exist in the graph (node labels)
ENTITY_TYPES = [
    "Person",
    "Team",
    "Project",
    "Decision",
    "Document",
    "Ticket",
    "SlackMessage",
]

# dataset section -> node label; every record becomes one node, MERGEd on its "id"
DATASET_SECTIONS = {
    "people": "Person",
    "teams": "Team",
    "projects": "Project",
    "tickets": "Ticket",
    "documents": "Document",
    "decisions": "Decision",
    "slack_messages": "SlackMessage",
}

# Relationship types between entities (edge type -> direction and meaning)
RELATIONSHIP_TYPES = {
    "OWNS": "(Person)-[:OWNS]->(Project): accountable owner",
    "SPONSORS": "(Person)-[:SPONSORS]->(Project): executive sponsor",
    "LEADS": "(Person)-[:LEADS]->(Team)",
    "MEMBER_OF": "(Person)-[:MEMBER_OF]->(Team)",
    "APPROVED": "(Person)-[:APPROVED]->(Decision)",
    "AUTHORED_BY": "(Document)-[:AUTHORED_BY]->(Person)",
    "ASSIGNED_TO": "(Ticket)-[:ASSIGNED_TO]->(Person)",
    "REPORTED_BY": "(Ticket)-[:REPORTED_BY]->(Person)",
    "POSTED": "(Person)-[:POSTED]->(SlackMessage)",
    "MENTIONS": "(SlackMessage)-[:MENTIONS]->(Project|Ticket)",
    "BELONGS_TO": "(Ticket)-[:BELONGS_TO]->(Project)",
    "BLOCKS": "(Ticket)-[:BLOCKS]->(Ticket)",
    "SPLIT_FROM": "(Ticket)-[:SPLIT_FROM]->(Ticket)",
    "RELATED_TO": "(Ticket)-[:RELATED_TO]->(Ticket)",
    "CONTRADICTS": "(Decision)-[:CONTRADICTS]->(Decision)",
    "SUPERSEDES": "(Decision|Document)-[:SUPERSEDES]->(Decision|Document): the newer one points at the older one",
    "AFFECTS": "(Decision)-[:AFFECTS]->(Project)",
    "DOCUMENTED_IN": "(Decision)-[:DOCUMENTED_IN]->(Document)",
    "ANNOUNCED_IN": "(Decision)-[:ANNOUNCED_IN]->(SlackMessage)",
    "TRIGGERED": "(Document)-[:TRIGGERED]->(Decision)",
    "DISSENTS": "(Person)-[:DISSENTS]->(Decision); carries the ids of the messages that show it in `sources`",
}

# edges built from a record's own id fields: section -> [(field, edge type, other label, direction)]
# direction "out": (record)-[:TYPE]->(other); "in": (other)-[:TYPE]->(record)
FIELD_EDGES = {
    "teams": [("lead_id", "LEADS", "Person", "in"), ("member_ids", "MEMBER_OF", "Person", "in")],
    "projects": [("owner_id", "OWNS", "Person", "in"), ("sponsor_id", "SPONSORS", "Person", "in")],
    "tickets": [("assignee_id", "ASSIGNED_TO", "Person", "out"), ("reporter_id", "REPORTED_BY", "Person", "out")],
    "documents": [("author_id", "AUTHORED_BY", "Person", "out")],
    "decisions": [("approver_id", "APPROVED", "Person", "in")],
    "slack_messages": [("user_id", "POSTED", "Person", "in")],
}

# the dataset's "relationships" section: list name -> (from label, from key, edge type, to label, to key,
# extra keys copied onto the edge)
RELATIONSHIP_SECTIONS = {
    "SLACK_MENTIONS_PROJECT": ("SlackMessage", "message_id", "MENTIONS", "Project", "project_id", ()),
    "SLACK_MENTIONS_TICKET": ("SlackMessage", "message_id", "MENTIONS", "Ticket", "ticket_id", ()),
    "TICKET_BELONGS_TO_PROJECT": ("Ticket", "ticket_id", "BELONGS_TO", "Project", "project_id", ()),
    "TICKET_BLOCKS_TICKET": ("Ticket", "ticket_id", "BLOCKS", "Ticket", "blocks", ()),
    "TICKET_SPLIT_FROM_TICKET": ("Ticket", "ticket_id", "SPLIT_FROM", "Ticket", "split_from", ("date", "sources")),
    "TICKET_RELATED_TO_TICKET": ("Ticket", "ticket_id", "RELATED_TO", "Ticket", "related_to", ()),
    "DECISION_CONTRADICTS_DECISION": ("Decision", "decision_id", "CONTRADICTS", "Decision", "contradicts", ()),
    "DECISION_SUPERSEDES_DECISION": ("Decision", "decision_id", "SUPERSEDES", "Decision", "supersedes", ()),
    "DECISION_AFFECTS_PROJECT": ("Decision", "decision_id", "AFFECTS", "Project", "project_id", ()),
    "DECISION_DOCUMENTED_IN": ("Decision", "decision_id", "DOCUMENTED_IN", "Document", "document_id", ()),
    "DECISION_ANNOUNCED_IN_SLACK": ("Decision", "decision_id", "ANNOUNCED_IN", "SlackMessage", "message_id", ()),
    "DOCUMENT_SUPERSEDES_DOCUMENT": ("Document", "document_id", "SUPERSEDES", "Document", "supersedes", ()),
    "DOCUMENT_TRIGGERED_DECISION": ("Document", "document_id", "TRIGGERED", "Decision", "decision_id", ()),
    "PERSON_DISSENTS_DECISION": ("Person", "person_id", "DISSENTS", "Decision", "decision_id", ("sources",)),
}

# never stored on a node: authoring commentary ("notes"), id fields that became edges above,
# and nested history that is not modelled yet
EXCLUDED_FIELDS = {"notes", "note", "history", "description_versions"} | {
    field for edges in FIELD_EDGES.values() for field, _, _, _ in edges
}

# properties that name a node, and that date it, in the order tools should try them
NAME_PROPERTIES = ["name", "title", "key", "channel"]
DATE_PROPERTIES = ["date", "created", "timestamp", "start_date"]

# Property aliases: canonical_name -> [aliases]
# Allows flexibility if companies use different field names
PROPERTY_ALIASES = {
    # Date properties
    "date": ["created_at", "created_date", "timestamp", "occurred_at", "updated_at"],
    "start_date": ["start", "started_at", "begin_date"],
    "end_date": ["end", "ended_at", "target_date", "due_date"],

    # Name/title properties
    "name": ["title", "label", "subject"],
    "title": ["name", "subject"],

    # Financial properties
    "budget": ["budget_usd", "budget_amount", "cost", "amount", "budget_gbp", "budget_eur"],

    # Status properties
    "status": ["state", "phase", "progress"],

    # Owner properties
    "owner": ["owned_by", "owner_id", "lead", "lead_id"],
    "author": ["created_by", "author_id", "writer"],

    # Identifier properties
    "id": ["key", "uid", "identifier"],
}

# Node properties the ingest script writes for each entity type (scalars as-is, lists of scalars as lists,
# anything nested as JSON text)
NODE_PROPERTIES = {
    "Person": {
        "required": ["id", "name"],
        "optional": ["email", "role", "department", "start_date", "reports_to", "team_id", CLEARANCE_PROPERTY],
    },
    "Team": {
        "required": ["id", "name"],
        "optional": [CLEARANCE_PROPERTY],
    },
    "Project": {
        "required": ["id", "name"],
        "optional": ["department", "status", "priority", "scope", "budget_usd", "target_end",
                     "ticket_ids", "decision_ids", "document_ids", CLEARANCE_PROPERTY],
    },
    "Decision": {
        "required": ["id", "title"],
        "optional": ["key", "date", "announced_date", "status", "description", "details", "rationale", "impact",
                     "superseded_by", "overrides", "reverses", "sources", "dissent", CLEARANCE_PROPERTY],
    },
    "Document": {
        "required": ["id", "title"],
        "optional": ["family", "version", "created", "status", "content", "key_facts", "supersedes",
                     "conflicts_with", "location", "format", CLEARANCE_PROPERTY],
    },
    "Ticket": {
        "required": ["id", "title"],
        "optional": ["key", "project_id", "status", "priority", "created", "resolved", "due_date", "budget_usd",
                     "description", "comments", "links", "blocker", "blockers", "resolution", "schedule",
                     "timeline", "requirements", "launch_target", CLEARANCE_PROPERTY],
    },
    "SlackMessage": {
        "required": ["id", "text"],
        "optional": ["channel", "username", "timestamp", "thread_ts", "reactions", "mentioned",
                     CLEARANCE_PROPERTY],
    },
}

# Conflict tracking edge types
CONFLICT_EDGES = [
    "CONTRADICTS",      # Statement A contradicts statement B
    "SUPERSEDES",       # Newer decision/document replaces an older one
    "CHANGED_TO",       # Value changed from X to Y
    "CONFLICTS_WITH",   # Generic conflict between any nodes
]

# Source authority hierarchy (for conflict resolution)
# Higher score = more authoritative
SOURCE_AUTHORITY = {
    "Decision": 10,      # Decisions are authoritative
    "Document": 8,       # Official documents are high-authority
    "Person": 6,         # People recounting facts
    "Ticket": 5,         # Tickets/issues
    "SlackMessage": 3,   # Slack messages are low-authority
}
