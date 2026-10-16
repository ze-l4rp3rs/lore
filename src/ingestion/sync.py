import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import schema
from src.retrieval.falkordb_client import get_client

BATCH_SIZE = 200
SCALARS = (str, int, float, bool)
MANIFEST_NAME = ".ingest_manifest.json"
MANIFEST_VERSION = 1


def sha256_file(
    path: str
) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


IGNORED_PREFIXES = (".", "#", ".~lock")
IGNORED_SUFFIXES = (".manifest.json", ".pyc", ".tmp", ".bak", ".swp", "~")


def _is_ignored(name: str) -> bool:
    return any(name.startswith(p) for p in IGNORED_PREFIXES) or any(name.endswith(s) for s in IGNORED_SUFFIXES)


def collect_sources(
    source: str
) -> tuple[str, bool, list[tuple[str, str]]]:
    # returns (base dir, is directory, [(key, absolute path)]). key is stable: the path relative to the
    # folder, or the file name. Hidden files and the manifest are never sources.
    if os.path.isdir(source):
        base = os.path.abspath(source)
        found = []
        for root, _, names in os.walk(base):
            for name in sorted(names):
                if not _is_ignored(name):
                    full = os.path.join(root, name)
                    found.append((os.path.relpath(full, base).replace(os.sep, "/"), full))
        if not found:
            raise ValueError(f"no source files under {source}")
        return base, True, found
    if os.path.isfile(source):
        base = os.path.dirname(os.path.abspath(source)) or "."
        return base, False, [(os.path.basename(source), os.path.abspath(source))]
    raise ValueError(f"source not found: {source}")


def parse_source(
    key: str,
    path: str
) -> dict | None:
    # A .json file is parsed as a structured dataset if it contains dataset sections or relationships.
    # Any other company document (PDF, DOCX, XML, Markdown, plain text, etc.) is extracted with
    # xberg into a Document node whose identity comes from its relative path/location.
    if key.lower().endswith(".json"):
        try:
            with open(path, encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict) and (
                any(section in data for section in schema.DATASET_SECTIONS) or "relationships" in data
            ):
                return data
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    try:
        from src.ingestion.extractor import ExtractionError, ExtractionUnavailable, extract_bytes

        with open(path, "rb") as file:
            data = file.read()
        text, meta = extract_bytes(data, filename=os.path.basename(path))
    except ExtractionUnavailable as caught:
        print(f"Warning: {caught}; skipped {key}")
        return None
    except ExtractionError as caught:
        print(f"Warning: could not extract {key}: {caught}; skipped")
        return None
    except Exception as caught:
        print(f"Warning: could not process {key}: {caught}; skipped")
        return None

    record = {
        "id": key,
        "title": meta.get("title") or os.path.basename(path),
        "content": text,
        "location": key,
        "clearance": schema.DEFAULT_CLEARANCE_LEVEL,
    }
    if meta.get("format"):
        record["format"] = meta["format"]
    return {"documents": [record]}


def default_manifest_path(
    source: str,
    is_dir: bool
) -> str:
    if is_dir:
        return os.path.join(os.path.abspath(source), MANIFEST_NAME)
    return os.path.join(os.path.dirname(os.path.abspath(source)) or ".", "." + os.path.basename(source) + ".manifest.json")


def load_manifest(
    path: str
) -> dict:
    if not os.path.isfile(path):
        return {"version": MANIFEST_VERSION, "files": {}}
    with open(path, encoding="utf-8") as file:
        manifest = json.load(file)
    manifest.setdefault("version", MANIFEST_VERSION)
    manifest.setdefault("files", {})
    return manifest


def save_manifest(
    path: str,
    manifest: dict
):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False, sort_keys=True)
        file.write("\n")


def clearance_of(
    record: dict
) -> int:
    value = record.get(schema.CLEARANCE_PROPERTY, schema.DEFAULT_CLEARANCE_LEVEL)
    if isinstance(value, bool) or not isinstance(value, int):
        try:
            value = int(value)
        except (TypeError, ValueError) as caught:
            raise ValueError(f"{record.get('id')}: clearance must be a whole number, got {value!r}") from caught
    if not (schema.MIN_CLEARANCE_LEVEL <= value <= schema.MAX_CLEARANCE_LEVEL):
        raise ValueError(
            f"{record.get('id')}: clearance {value} is outside "
            f"{schema.MIN_CLEARANCE_LEVEL}..{schema.MAX_CLEARANCE_LEVEL}"
        )
    return value


def node_properties(
    record: dict
) -> dict:
    # scalars and lists of scalars are stored as they are; anything nested becomes JSON text.
    # every record gets its clearance, defaulted when the source omits it.
    properties = {}
    for key, value in record.items():
        if key in schema.EXCLUDED_FIELDS or value is None:
            continue
        if isinstance(value, SCALARS) or (isinstance(value, list) and all(isinstance(item, SCALARS) for item in value)):
            properties[key] = value
        else:
            properties[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    properties[schema.CLEARANCE_PROPERTY] = clearance_of(record)
    return properties


def plan_nodes(
    data: dict
) -> tuple[dict[str, list[dict]], dict[str, list[str]]]:
    # label -> property maps, and label -> ids, for one source file
    nodes: dict[str, list[dict]] = {}
    ids: dict[str, list[str]] = {}
    for section, label in schema.DATASET_SECTIONS.items():
        rows, row_ids = [], []
        for record in data.get(section, []) or []:
            if not record.get("id"):
                raise ValueError(f"{section}: record without an id: {record}")
            rows.append(node_properties(record))
            row_ids.append(record["id"])
        if rows:
            nodes[label] = rows
            ids[label] = row_ids
    return nodes, ids


def _as_list(
    value
) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def plan_edges(
    data: dict,
    labels: dict[str, str],
    origin: str
) -> dict[tuple[str, str, str], list[dict]]:
    # (from label, edge type, to label) -> [{"from", "to", "props"}], each edge once, attributed to origin
    edges: dict[tuple[str, str, str], list[dict]] = {}
    seen: set[tuple[str, str, str]] = set()

    def add(from_label, from_id, edge_type, to_label, to_id, props, where, row):
        for label, node_id in ((from_label, from_id), (to_label, to_id)):
            if labels.get(node_id) != label:
                raise ValueError(f"{where}: {node_id!r} is not a {label} id anywhere in this source. Row: {row}")
        if (from_id, edge_type, to_id) in seen:
            return
        seen.add((from_id, edge_type, to_id))
        edges.setdefault((from_label, edge_type, to_label), []).append(
            {"from": from_id, "to": to_id, "props": {**props, "origin": origin}}
        )

    for section, specs in schema.FIELD_EDGES.items():
        label = schema.DATASET_SECTIONS[section]
        for record in data.get(section, []) or []:
            for field, edge_type, other, direction in specs:
                for other_id in _as_list(record.get(field)):
                    ends = [(label, record["id"]), (other, other_id)]
                    if direction == "in":
                        ends.reverse()
                    add(*ends[0], edge_type, *ends[1], {}, f"{origin}:{section}[{record['id']}].{field}", record)

    for name, rows in (data.get("relationships", {}) or {}).items():
        if name not in schema.RELATIONSHIP_SECTIONS:
            print(f"Warning: relationships.{name} in {origin} is not described in schema.py; skipped")
            continue
        from_label, from_key, edge_type, to_label, to_key, extra = schema.RELATIONSHIP_SECTIONS[name]
        for row in rows:
            props = {key: row[key] for key in extra if row.get(key) is not None}
            add(from_label, row.get(from_key), edge_type, to_label, row.get(to_key), props, f"{origin}:relationships.{name}", row)
    return edges


def _write_batches(
    client,
    cypher: str,
    rows: list[dict],
    what: str
) -> int:
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        try:
            client.write(cypher, {"rows": batch})
        except Exception:
            for row in batch:
                try:
                    client.write(cypher, {"rows": [row]})
                except Exception as caught:
                    raise RuntimeError(f"{what}: could not write {row}: {caught}") from caught
            raise
    return len(rows)


def sync(
    source: str,
    client=None,
    manifest_path: str | None = None,
    dry_run: bool = False
) -> dict:
    """Incrementally reconcile the graph with a folder (or single file) of source data.

    Accepts structured .json datasets as well as company documents (PDF, DOCX, XML, Markdown,
    plain text, etc.). Documents are extracted with xberg into Document nodes. Nodes are MERGEd on
    id, never bulk-cleared. A source file that changed has its old edges replaced; a node id that no
    longer appears in any source is deleted (with its edges). Unchanged files are skipped.
    """
    base, is_dir, sources = collect_sources(source)
    manifest_path = manifest_path or default_manifest_path(source, is_dir)
    manifest = load_manifest(manifest_path)

    parsed: list[tuple[str, dict]] = []
    hashes: dict[str, str] = {}
    for key, path in sources:
        data = parse_source(key, path)
        if data is None:
            continue
        hashes[key] = sha256_file(path)
        parsed.append((key, data))

    # plan nodes for every file; ids are unique across the whole source
    per_file_nodes: dict[str, dict] = {}
    per_file_ids: dict[str, dict] = {}
    labels: dict[str, str] = {}
    owner: dict[str, str] = {}
    for key, data in parsed:
        nodes, ids = plan_nodes(data)
        per_file_nodes[key] = nodes
        per_file_ids[key] = ids
        for label, row_ids in ids.items():
            for node_id in row_ids:
                if node_id in labels:
                    raise ValueError(f"id {node_id!r} appears in both {owner[node_id]} and {key}; ids must be unique")
                labels[node_id] = label
                owner[node_id] = key

    # plan edges across the whole source, so an edge is written once and attributed to the first file
    data_by_key = dict(parsed)
    edges: dict[tuple[str, str, str], list[dict]] = {}
    seen_edges: set[tuple[str, str, str]] = set()
    for key in sorted(data_by_key):
        for signature, rows in plan_edges(data_by_key[key], labels, key).items():
            kept = []
            for row in rows:
                marker = (row["from"], signature[1], row["to"])
                if marker in seen_edges:
                    continue
                seen_edges.add(marker)
                kept.append(row)
            if kept:
                edges.setdefault(signature, []).extend(kept)

    previous = manifest.get("files", {})
    current = set(hashes)
    added = sorted(current - set(previous))
    removed = sorted(set(previous) - current)
    changed = sorted(key for key in current & set(previous) if previous[key].get("sha256") != hashes[key])
    unchanged = sorted(key for key in current & set(previous) if previous[key].get("sha256") == hashes[key])

    old_ids = {node_id for entry in previous.values() for row_ids in entry.get("nodes", {}).values() for node_id in row_ids}
    delete_ids = sorted(old_ids - set(labels))
    touch = set(added) | set(changed)

    planned_nodes = sum(len(rows) for key in touch for rows in per_file_nodes[key].values())
    planned_edges = sum(
        len([row for row in rows if row["props"]["origin"] in touch])
        for rows in edges.values()
    )

    report = {
        "added": added,
        "changed": changed,
        "removed": removed,
        "unchanged": unchanged,
        "nodes_written": planned_nodes if dry_run else 0,
        "nodes_deleted": len(delete_ids),
        "edges_written": planned_edges if dry_run else 0,
        "edges_deleted": 0,
        "manifest_path": manifest_path,
        "dry_run": dry_run,
    }
    if dry_run:
        return report

    client = client or get_client()
    if not client.available:
        raise SystemExit("ERROR: Could not connect to FalkorDB. Is it running?")

    # 1. forget nodes that no source defines any more (never a blanket clear)
    if delete_ids:
        client.write("UNWIND $ids AS id MATCH (n {id: id}) DETACH DELETE n", {"ids": delete_ids})

    # 2. drop the edges owned by files that changed or disappeared; steps 3-4 put the current ones back
    for key in sorted(set(changed) | set(removed)):
        result = client.write("MATCH (a)-[r]->(b) WHERE r.origin = $origin DELETE r", {"origin": key})
        report["edges_deleted"] += int(getattr(result, "relationships_deleted", 0) or 0)

    # 3. write nodes for added and changed files (replace properties, so dropped fields disappear)
    for key in sorted(touch):
        for label, rows in per_file_nodes[key].items():
            print(f"{key}: {len(rows)} {label} nodes")
            report["nodes_written"] += _write_batches(
                client, f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n = row", rows, label
            )

    # 4. write edges for added and changed files
    for (from_label, edge_type, to_label), rows in edges.items():
        rows = [row for row in rows if row["props"]["origin"] in touch]
        if not rows:
            continue
        print(f"{len(rows)} {from_label}-{edge_type}->{to_label} edges")
        cypher = (
            f"UNWIND $rows AS row "
            f"MATCH (a:{from_label} {{id: row.from}}) MATCH (b:{to_label} {{id: row.to}}) "
            f"MERGE (a)-[r:{edge_type}]->(b) SET r = row.props"
        )
        report["edges_written"] += _write_batches(client, cypher, rows, f"{from_label}-{edge_type}->{to_label}")

    # 5. remember what each file holds, so the next run can tell what changed
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for key in touch:
        previous[key] = {"sha256": hashes[key], "ingestedAt": now, "nodes": per_file_ids[key]}
    for key in removed:
        previous.pop(key, None)
    manifest["source"] = base if is_dir else os.path.abspath(source)
    manifest["updatedAt"] = now
    save_manifest(manifest_path, manifest)
    print(f"Manifest: {manifest_path}")
    return report
