import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# [[cite:<id>]] or [[cite:<id>|<words copied exactly from that source>]]
CITATION_RE = re.compile(r"\[\[cite:([0-9a-f]{8})(?:\|(.+?))?\]\]")


def clean_quote(
    quote: str | None
) -> str:
    return (quote or "").strip().strip("\"'“”‘’").strip()
