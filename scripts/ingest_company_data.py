#!/usr/bin/env python3
"""Reconcile FalkorDB with a folder of source data (.json datasets or documents like PDF, DOCX, XML, Markdown, text).

Point it at a folder (default: data/) of source files, or at a single file. Each file is planned,
content-hashed and remembered in a manifest next to the source. On the next run only added and changed
files are written; a changed file's old edges are replaced and any node id that no longer appears in any
file is deleted. Nothing else is ever cleared. See README "Ingesting data".
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.sync import sync


def main() -> int:
    parser = argparse.ArgumentParser(description="Incrementally load company data into FalkorDB.")
    parser.add_argument("source", nargs="?", default="data",
                        help="folder of source files (.json, .pdf, .docx, .xml, .md, etc.) or a single file (default: data)")
    parser.add_argument("--manifest", help="manifest path (default: alongside the source)")
    parser.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f"ERROR: source not found: {args.source}")
        return 1

    try:
        report = sync(args.source, manifest_path=args.manifest, dry_run=args.dry_run)
    except SystemExit as caught:
        print(caught)
        return 1
    except ValueError as caught:
        print(f"ERROR: {caught}")
        return 1

    prefix = "=== DRY RUN: Planning reconciliation for" if args.dry_run else "=== Reconciled"
    print(f"\n{prefix} '{args.source}' ===")
    print("\nSource Files:")
    if report["added"]:
        print(f"  + Added ({len(report['added'])}):")
        for f in report["added"]:
            print(f"      {f}")
    if report["changed"]:
        print(f"  ~ Changed ({len(report['changed'])}):")
        for f in report["changed"]:
            print(f"      {f}")
    if report["removed"]:
        print(f"  - Removed ({len(report['removed'])}):")
        for f in report["removed"]:
            print(f"      {f}")
    if report["unchanged"]:
        count = len(report["unchanged"])
        if count <= 4:
            print(f"  = Unchanged ({count}): {', '.join(report['unchanged'])}")
        else:
            print(f"  = Unchanged: {count} files")
    if not any((report["added"], report["changed"], report["removed"], report["unchanged"])):
        print("  (No files found)")

    label = "\nPlanned Graph Changes:" if args.dry_run else "\nGraph Changes Applied:"
    print(label)
    nodes_action = "Nodes to write" if args.dry_run else "Nodes written"
    edges_action = "Edges to write" if args.dry_run else "Edges written"

    del_nodes = f" ({report['nodes_deleted']} to delete)" if args.dry_run and report["nodes_deleted"] else (
        f" ({report['nodes_deleted']} deleted)" if report["nodes_deleted"] else ""
    )
    del_edges = f" ({report['edges_deleted']} to delete)" if args.dry_run and report["edges_deleted"] else (
        f" ({report['edges_deleted']} deleted)" if report["edges_deleted"] else ""
    )

    print(f"  • {nodes_action}: {report['nodes_written']}{del_nodes}")
    print(f"  • {edges_action}: {report['edges_written']}{del_edges}")

    if args.dry_run:
        print("\n✓ Dry run complete. No changes were written to the database.\n")
    else:
        manifest = report.get("manifest_path")
        if manifest:
            print(f"\n✓ Ingestion complete. Manifest updated: {manifest}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
