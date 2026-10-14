import sys
import os
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.validations import CITATION_RE
from src.workflow.reflexion import RunResult


def format_answer(
    text: str
) -> str:
    # [[cite:<id>|<quote>]] -> [[<id>]]: the frontend renders the marker inline or as a footnote
    return CITATION_RE.sub(lambda match: f"[[{match.group(1)}]]", text)


def build_response(
    result: RunResult
) -> dict[str, Any]:
    # the one JSON shape the CLI and the API both return; later changes only add fields
    return {
        "answer": format_answer(result.answer),
        "references": [
            {
                "id": source["id"],
                "number": source["number"],
                "type": source["type"],
                "title": source["label"],
                "excerpt": source["quotes"][0] if source["quotes"] else "",
                "quotes": source["quotes"],
                "date": source["date"],
                "url": source["url"],  # empty when the source has no link
                "nodeId": source["ref"] or f"{source['type']}:{source['label']}",
                "meta": source["meta"],
            }
            for source in result.sources
        ],
        "status": result.status,
        "unverified": result.unverified,
        "missing": result.missing,
        "premise": result.premise,
        "metadata": {
            "rounds": result.rounds,
            "approved": result.status == "verified",
            "processingTimeMs": result.elapsed_ms,
        },
    }
