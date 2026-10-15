# src/tools/falkordb_query.py
"""Tool for querying FalkorDB graph: natural language mapped to fixed parameterised Cypher, or read-only Cypher."""

import hashlib
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import schema
from src.retrieval.falkordb_client import get_client
from src.validations import Evidence, Note

MAX_ROWS = 15  # each row is its own citable source; more than this is cut, and the result says so

# raw Cypher is recognised FIRST, by its opening clause
# a question that merely starts with "with", "match" or "call" ("with whom does Ana work") is not Cypher:
# a pattern needs MATCH ( ... ), and the other openers need a RETURN or a db.* procedure call somewhere
_CYPHER_START = re.compile(r"^\s*(?:OPTIONAL\s+MATCH|MATCH)\s*\(", re.IGNORECASE)
_CYPHER_OTHER = re.compile(r"^\s*(?:WITH|RETURN|UNWIND|CALL)\b", re.IGNORECASE)
_CYPHER_BODY = re.compile(r"\bRETURN\b|\bCALL\s+db\.", re.IGNORECASE)
_WRITE_CLAUSE = re.compile(r"\b(?:CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|FOREACH)\b", re.IGNORECASE)
_CALL = re.compile(r"\bCALL\b", re.IGNORECASE)
_READ_PROCEDURE = re.compile(r"\bCALL\s+db\.(?:labels|relationshipTypes|propertyKeys)\s*\(\s*\)", re.IGNORECASE)
_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")

# words that name an entity type in a question -> node label
_TYPE_WORDS = {
    "people": "Person", "person": "Person", "persons": "Person", "employees": "Person",
    "team": "Team", "teams": "Team",
    "project": "Project", "projects": "Project",
    "decision": "Decision", "decisions": "Decision",
    "document": "Document", "documents": "Document", "docs": "Document",
    "ticket": "Ticket", "tickets": "Ticket",
    "message": "SlackMessage", "messages": "SlackMessage",
}
_STOPWORDS = {
    "the", "a", "an", "of", "on", "in", "to", "for", "and", "or", "is", "are", "was", "were", "be", "been",
    "who", "what", "which", "when", "where", "why", "how", "does", "did", "do", "about", "with", "from",
    "find", "show", "list", "all", "me", "tell", "give", "any", "this", "that", "there", "their", "its", "has", "have",
}
_LEADING_FILLER = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)

# a node's display name and the text a keyword search looks in
_NAME = "coalesce(" + ", ".join(f"entity.{name}" for name in schema.NAME_PROPERTIES) + ", '')"
_HAYSTACK = ("toLower(coalesce(n.name, '') + ' ' + coalesce(n.title, '') + ' ' + coalesce(n.key, '') + ' ' + "
             "coalesce(n.text, '') + ' ' + coalesce(n.content, '') + ' ' + coalesce(n.description, ''))")

OWNERS = f"""
MATCH (owner)-[:OWNS]->(entity)
WHERE toLower({_NAME}) CONTAINS $term
RETURN owner.name AS owner, owner.role AS owner_role, {_NAME} AS owns, labels(entity) AS entity_type
LIMIT $limit
"""

INVOLVED = f"""
MATCH (person:Person)-[rel]-(entity)
WHERE NOT entity:Person AND toLower({_NAME}) CONTAINS $term
RETURN person.name AS person, type(rel) AS relationship, {_NAME} AS entity, labels(entity) AS entity_type
LIMIT $limit
"""

SEARCH = f"""
MATCH (n)
WITH n, {_HAYSTACK} AS haystack
WITH n, size([term IN $terms WHERE haystack CONTAINS term]) AS hits
WHERE hits > 0
RETURN n AS node, labels(n) AS type
ORDER BY hits DESC
LIMIT $limit
"""


def _words(
    text: str
) -> list[str]:
    return re.findall(r"[\w$#.-]+", text.lower())


def _after(
    pattern: str,
    query: str
) -> str:
    # the words after the first whole-word match, e.g. the entity in "who owns <entity>?"
    match = re.search(pattern, query, re.IGNORECASE)
    if not match:
        return ""
    return _LEADING_FILLER.sub("", query[match.end():].strip(" ?.!\"'")).strip()


def check_read_only(
    cypher: str
):
    # string literals may contain any words; only the query structure is checked
    structure = _STRING_LITERAL.sub("''", cypher)
    found = _WRITE_CLAUSE.search(structure)
    if found:
        raise ValueError(f"read-only queries only: {found.group(0).upper()} is not allowed")
    if len(_CALL.findall(structure)) != len(_READ_PROCEDURE.findall(structure)):
        raise ValueError("read-only queries only: CALL is limited to db.labels(), db.relationshipTypes(), db.propertyKeys()")


def plan_query(
    query: str
) -> tuple[str, dict]:
    """Return (cypher, params) for a natural-language question or a raw Cypher query."""
    if _CYPHER_START.match(query) or (_CYPHER_OTHER.match(query) and _CYPHER_BODY.search(query)):
        check_read_only(query)
        return query, {}

    tokens = _words(query)
    words = set(tokens)
    limit = MAX_ROWS + 1  # one extra row tells us the result was cut

    if "who" in words and (words & {"own", "owns", "owner", "owned"} or re.search(r"\bresponsible for\b", query, re.I)):
        term = _after(r"\b(?:owns?|owner of|owned|responsible for)\b", query)
        if term:
            return OWNERS, {"term": term.lower(), "limit": limit}

    if "who" in words and words & {"work", "works", "working", "worked", "involved"}:
        term = _after(r"\b(?:on|with|in)\b", query)
        if term:
            return INVOLVED, {"term": term.lower(), "limit": limit}

    if words & {"list", "show", "all"}:
        labels = [_TYPE_WORDS[word] for word in tokens if word in _TYPE_WORDS]
        if labels:
            return f"MATCH (n:{labels[0]}) RETURN n AS node ORDER BY n.id LIMIT $limit", {"limit": limit}

    terms = sorted({word for word in tokens if word not in _STOPWORDS and len(word) > 2})
    if not terms:
        raise ValueError("nothing to search for; name an entity or write a read-only Cypher query")
    return SEARCH, {"terms": terms, "limit": limit}


def _row_text(
    row: dict
) -> str:
    parts = []
    for key, value in row.items():
        if isinstance(value, dict):  # a whole node: its own properties
            value = ", ".join(f"{k}: {v}" for k, v in value.items() if not k.startswith("_") and v not in (None, "", []))
        if value in (None, "", []):
            continue
        parts.append(f"{key}: {value}")
    return " | ".join(parts)


def _evidence(
    row: dict,
    text: str
) -> Evidence:
    # a row that is one graph node becomes a source of that node's type, named and dated from its own
    # properties, and identified by the node id, so the same node found by two queries is one source;
    # any other row (columns, several nodes) is a "query_result" identified by its text
    nodes = [value for value in row.values() if isinstance(value, dict)]
    node = nodes[0] if len(nodes) == 1 else None
    meta = {key: value for key, value in row.items() if not isinstance(value, dict)}
    if node is None or not node.get("id"):
        return Evidence(
            kind="query_result",
            label=f"Result: {text[:60]}",
            text=text,
            ref="query:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],  # stable across processes
            meta=meta,
        )
    labels = node.get("_labels") or row.get("type") or row.get("entity_type") or []
    label = next((str(node[name]) for name in schema.NAME_PROPERTIES if node.get(name)), str(node["id"]))
    return Evidence(
        kind=str(labels[0]).lower() if labels else "node",
        label=label,
        text=text,
        date=next((str(node[name]) for name in schema.DATE_PROPERTIES if node.get(name)), ""),
        ref=str(node["id"]),
        meta=meta,
    )


def falkordb_query(query: str) -> list[Evidence | Note]:
    """
    Query FalkorDB graph using natural language or read-only Cypher.

    Handles:
    - "Who owns X?" -> owners of matching entities
    - "Who works on / is involved with X?" -> people connected to matching entities
    - "List all <type>" -> nodes of that type
    - anything else -> keyword search over names, titles and text
    - Cypher starting with MATCH / WITH / RETURN / UNWIND -> run read-only

    Each result row becomes its own citable source; a cut-off result adds a Note, which is not a source.
    Failures raise; they never become sources.
    """
    client = get_client()
    if not client.available:
        raise RuntimeError("FalkorDB is not available")

    cypher, params = plan_query(query.strip())
    rows = client.query(cypher, params)

    evidence_list = []
    for row in rows[:MAX_ROWS]:
        text = _row_text(row)
        if not text:
            continue
        evidence_list.append(_evidence(row, text))
    if len(rows) > MAX_ROWS:
        evidence_list.append(Note(f"Only the first {MAX_ROWS} rows are shown; more matched. Narrow the query to see the rest."))
    return evidence_list
