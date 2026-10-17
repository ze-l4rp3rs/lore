# src/tools/falkordb_query.py
"""Tool for querying FalkorDB graph: natural language mapped to fixed parameterised Cypher, or read-only Cypher."""

import hashlib
import re
import os

import config
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
_NAME = "coalesce(" + ", ".join(f"entity.{name}" for name in config.NAME_PROPERTIES) + ", '')"
_HAYSTACK = ("toLower(coalesce(n.name, '') + ' ' + coalesce(n.title, '') + ' ' + coalesce(n.key, '') + ' ' + "
             "coalesce(n.text, '') + ' ' + coalesce(n.content, '') + ' ' + coalesce(n.description, ''))")

# every fixed query only touches nodes at or below the asker's clearance ($max_clearance); a node
# without one counts as the most open level
def _clear(node: str) -> str:
    return f"coalesce({node}.clearance, $default_clearance) <= $max_clearance"

OWNERS = f"""
MATCH (owner)-[:OWNS]->(entity)
WHERE toLower({_NAME}) CONTAINS $term AND {_clear("owner")} AND {_clear("entity")}
RETURN owner.name AS owner, owner.role AS owner_role, {_NAME} AS owns, labels(entity) AS entity_type
LIMIT $limit
"""

INVOLVED = f"""
MATCH (person:Person)-[rel]-(entity)
WHERE NOT entity:Person AND toLower({_NAME}) CONTAINS $term AND {_clear("person")} AND {_clear("entity")}
RETURN person.name AS person, type(rel) AS relationship, {_NAME} AS entity, labels(entity) AS entity_type
LIMIT $limit
"""

SEARCH = f"""
MATCH (n)
WHERE {_clear("n")}
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
    query: str,
    max_clearance: int = config.MAX_CLEARANCE_LEVEL
) -> tuple[str, dict, bool]:
    """Return (cypher, params, is_raw_cypher) for a natural-language question or a raw Cypher query.

    Template queries carry a clearance filter that only returns nodes at or below `max_clearance`.
    Raw Cypher is run as written and filtered afterwards by row.
    """
    if _CYPHER_START.match(query) or (_CYPHER_OTHER.match(query) and _CYPHER_BODY.search(query)):
        check_read_only(query)
        return query, {}, True

    tokens = _words(query)
    words = set(tokens)
    limit = MAX_ROWS + 1  # one extra row tells us the result was cut
    limit_params = {"limit": limit, "max_clearance": max_clearance, "default_clearance": config.DEFAULT_CLEARANCE_LEVEL}

    if "who" in words and (words & {"own", "owns", "owner", "owned"} or re.search(r"\bresponsible for\b", query, re.I)):
        term = _after(r"\b(?:owns?|owner of|owned|responsible for)\b", query)
        if term:
            return OWNERS, {"term": term.lower(), **limit_params}, False

    if "who" in words and words & {"work", "works", "working", "worked", "involved"}:
        term = _after(r"\b(?:on|with|in)\b", query)
        if term:
            return INVOLVED, {"term": term.lower(), **limit_params}, False

    if words & {"list", "show", "all"}:
        labels = [_TYPE_WORDS[word] for word in tokens if word in _TYPE_WORDS]
        if labels:
            cypher = (f"MATCH (n:{labels[0]}) WHERE {_clear('n')} RETURN n AS node ORDER BY n.id LIMIT $limit")
            return cypher, dict(limit_params), False

    terms = sorted({word for word in tokens if word not in _STOPWORDS and len(word) > 2})
    if not terms:
        raise ValueError("nothing to search for; name an entity or write a read-only Cypher query")
    return SEARCH, {"terms": terms, **limit_params}, False

def _visible(
    rows: list[dict],
    max_clearance: int
) -> list[dict]:
    # raw Cypher is not rewritten, so drop any row that returns a node above the asker's clearance;
    # a node without a clearance counts as the most open level
    visible = []
    for row in rows:
        if all(
            not isinstance(value, dict)
            or value.get(config.CLEARANCE_PROPERTY) is None
            or int(value[config.CLEARANCE_PROPERTY]) <= max_clearance
            for value in row.values()
        ):
            visible.append(row)
    return visible

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
    label = next((str(node[name]) for name in config.NAME_PROPERTIES if node.get(name)), str(node["id"]))
    return Evidence(
        kind=str(labels[0]).lower() if labels else "node",
        label=label,
        text=text,
        date=next((str(node[name]) for name in config.DATE_PROPERTIES if node.get(name)), ""),
        ref=str(node["id"]),
        meta=meta,
    )

def falkordb_query(
    query: str,
    user=None
) -> list[Evidence | Note]:
    """
    Query FalkorDB graph using natural language or read-only Cypher.

    Handles:
    - "Who owns X?" -> owners of matching entities
    - "Who works on / is involved with X?" -> people connected to matching entities
    - "List all <type>" -> nodes of that type
    - anything else -> keyword search over names, titles and text
    - Cypher starting with MATCH / WITH / RETURN / UNWIND -> run read-only

    Only nodes at or below the asker's clearance level are returned. Each result row becomes its own
    citable source; a cut-off result adds a Note, which is not a source. Failures raise; they never
    become sources.
    """
    max_clearance = getattr(user, "level", None)
    max_clearance = config.MAX_CLEARANCE_LEVEL if max_clearance is None else int(max_clearance)

    client = get_client()
    if not client.available:
        raise RuntimeError("FalkorDB is not available")

    cypher, params, is_raw = plan_query(query.strip(), max_clearance=max_clearance)
    rows = _visible(client.query(cypher, params), max_clearance) if is_raw else client.query(cypher, params)

    evidence_list = []
    for row in rows[:MAX_ROWS]:
        text = _row_text(row)
        if not text:
            continue
        evidence_list.append(_evidence(row, text))
    if len(rows) > MAX_ROWS:
        evidence_list.append(Note(f"Only the first {MAX_ROWS} rows are shown; more matched. Narrow the query to see the rest."))
    return evidence_list
