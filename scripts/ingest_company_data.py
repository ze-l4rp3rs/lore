#!/usr/bin/env python3
"""Ingest company data JSON into FalkorDB.

Every record becomes a node MERGEd on its id, every reference an edge MERGEd on (from, type, to), all
through UNWIND with parameters, so the load is idempotent and values are never pasted into Cypher.
Labels, edge types and the fields that are never stored ("notes": authoring commentary) come from schema.py.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema
from src.retrieval.falkordb_client import get_client

BATCH_SIZE = 200
SCALARS = (str, int, float, bool)


def as_list(
    value
) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def node_properties(
    record: dict
) -> dict:
    # scalars and lists of scalars are stored as they are; anything nested becomes JSON text
    properties = {}
    for key, value in record.items():
        if key in schema.EXCLUDED_FIELDS or value is None:
            continue
        if isinstance(value, SCALARS) or (isinstance(value, list) and all(isinstance(item, SCALARS) for item in value)):
            properties[key] = value
        else:
            properties[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return properties


def plan_nodes(
    data: dict
) -> dict[str, list[dict]]:
    # label -> one property map per record
    nodes: dict[str, list[dict]] = {}
    for section, label in schema.DATASET_SECTIONS.items():
        rows = []
        for record in data.get(section, []):
            if not record.get("id"):
                raise ValueError(f"{section}: record without an id: {record}")
            rows.append(node_properties(record))
        nodes[label] = rows
    return nodes


def plan_edges(
    data: dict,
    labels: dict[str, str]
) -> dict[tuple[str, str, str], list[dict]]:
    # (from label, edge type, to label) -> [{"from": id, "to": id, "props": {...}}], each edge once
    edges: dict[tuple[str, str, str], list[dict]] = {}
    seen: set[tuple[str, str, str]] = set()

    def add(from_label, from_id, edge_type, to_label, to_id, props, where, row):
        for label, node_id in ((from_label, from_id), (to_label, to_id)):
            if labels.get(node_id) != label:
                raise ValueError(f"{where}: {node_id!r} is not a {label} id in this dataset. Row: {row}")
        if (from_id, edge_type, to_id) in seen:
            return
        seen.add((from_id, edge_type, to_id))
        edges.setdefault((from_label, edge_type, to_label), []).append({"from": from_id, "to": to_id, "props": props})

    for section, specs in schema.FIELD_EDGES.items():
        label = schema.DATASET_SECTIONS[section]
        for record in data.get(section, []):
            for field, edge_type, other, direction in specs:
                for other_id in as_list(record.get(field)):
                    ends = [(label, record["id"]), (other, other_id)]
                    if direction == "in":
                        ends.reverse()
                    add(*ends[0], edge_type, *ends[1], {}, f"{section}[{record['id']}].{field}", record)

    for name, rows in data.get("relationships", {}).items():
        if name not in schema.RELATIONSHIP_SECTIONS:
            print(f"Warning: relationships.{name} is not described in schema.py; skipped")
            continue
        from_label, from_key, edge_type, to_label, to_key, extra = schema.RELATIONSHIP_SECTIONS[name]
        for row in rows:
            props = {key: row[key] for key in extra if row.get(key) is not None}
            add(from_label, row.get(from_key), edge_type, to_label, row.get(to_key), props, f"relationships.{name}", row)
    return edges


def write_rows(
    client,
    cypher: str,
    rows: list[dict],
    what: str
):
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        try:
            client.write(cypher, {"rows": batch})
        except Exception:
            # find the row that breaks the batch, so the error names it (MERGE makes the retry harmless)
            for row in batch:
                try:
                    client.write(cypher, {"rows": [row]})
                except Exception as caught:
                    raise RuntimeError(f"{what}: could not write {row}: {caught}") from caught
            raise


def ingest_data(
    data_file: str,
    client=None
) -> dict:
    """Load JSON data and ingest into FalkorDB. Returns the counts written."""

    # Load JSON
    print(f"Loading {data_file}...")
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)

    # plan everything first: a bad reference fails before anything is written
    nodes = plan_nodes(data)
    labels = {row["id"]: label for label, rows in nodes.items() for row in rows}
    edges = plan_edges(data, labels)

    client = client or get_client()
    if not client.available:
        raise SystemExit("ERROR: Could not connect to FalkorDB. Is it running?")

    # a re-run rebuilds the same graph from scratch
    print("Clearing existing data...")
    client.write("MATCH (n) DETACH DELETE n")

    for label, rows in nodes.items():
        print(f"Ingesting {len(rows)} {label} nodes...")
        write_rows(client, f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row", rows, label)

    for (from_label, edge_type, to_label), rows in edges.items():
        print(f"Creating {len(rows)} {from_label}-{edge_type}->{to_label} relationships...")
        cypher = (
            f"UNWIND $rows AS row "
            f"MATCH (a:{from_label} {{id: row.from}}) MATCH (b:{to_label} {{id: row.to}}) "
            f"MERGE (a)-[r:{edge_type}]->(b) SET r += row.props"
        )
        write_rows(client, cypher, rows, f"{from_label}-{edge_type}->{to_label}")

    counts = {"nodes": sum(len(rows) for rows in nodes.values()), "edges": sum(len(rows) for rows in edges.values())}

    # Verify
    stored = client.query("MATCH (n) RETURN count(n) AS nodes")
    stored_edges = client.query("MATCH ()-[r]->() RETURN count(r) AS edges")
    if stored and stored_edges:
        print(f"✓ Ingestion complete: {stored[0]['nodes']} nodes, {stored_edges[0]['edges']} edges")
    return counts


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest_company_data.py <data_file.json>")
        sys.exit(1)

    data_file = sys.argv[1]

    if not os.path.isfile(data_file):
        print(f"ERROR: File not found: {data_file}")
        sys.exit(1)

    try:
        ingest_data(data_file)
        print("✓ Data ingested successfully")
    except KeyboardInterrupt:
        print("\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
