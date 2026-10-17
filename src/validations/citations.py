import re
import unicodedata
import os

from src.validations.sources import SourceRegistry

# [[cite:<id>]] or [[cite:<id>|<words copied exactly from that source>]]; models drift to other
# separators (# > -> :), so those are accepted here and rewritten to "|" by repair_citations
_SEPARATORS = r"[|#>→:]"
_ID = r"([0-9a-f]{8})"  # sources.py makes ids with secrets.token_hex(4)
# the closing ]] must not be followed by another ], so a quote that itself ends in "]" keeps it
CITATION_RE = re.compile(r"\[\[cite:" + _ID + r"(?:" + _SEPARATORS + r"(.+?))?\]\](?!\])")

# near-miss syntax we can fix without asking the model: one bracket short on either side
_SHORT_CLOSE = re.compile(r"\[\[cite:" + _ID + r"(" + _SEPARATORS + r"[^\[\]\n]*?)?\](?!\])")
_SHORT_OPEN = re.compile(r"(?<!\[)\[cite:" + _ID + r"(" + _SEPARATORS + r"[^\[\]\n]*?)?\]\]")

_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…)\s*")
_FOLD = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ",
})

def _normalize(
    text: str
) -> str:
    # forgive case, whitespace, and typographic quotes/dashes; nothing else
    return " ".join(unicodedata.normalize("NFKC", text).translate(_FOLD).lower().split())

def clean_quote(
    quote: str | None
) -> str:
    return (quote or "").strip().strip("\"'“”‘’").strip()

def quote_in_source(
    quote: str,
    source_text: str
) -> bool:
    # "a ... b" means: a, then later b, both verbatim
    haystack = _normalize(source_text)
    start = 0
    pieces = [piece for piece in (_normalize(p) for p in _ELLIPSIS.split(quote)) if piece]
    if not pieces:
        return False
    for piece in pieces:
        found = haystack.find(piece, start)
        if found < 0:
            return False
        start = found + len(piece)
    return True

def repair_citations(
    text: str,
    registry: SourceRegistry
) -> tuple[str, list[str]]:
    # deterministic syntax fixes (brackets, separators), so they never cost a model call; quotes are never altered
    repairs: list[str] = []
    fixed = _SHORT_CLOSE.sub(lambda m: f"[[cite:{m.group(1)}{m.group(2) or ''}]]", text)
    fixed = _SHORT_OPEN.sub(lambda m: f"[[cite:{m.group(1)}{m.group(2) or ''}]]", fixed)
    if fixed != text:
        repairs.append("closed malformed citation brackets")

    separators_fixed = False

    def fix_quote(match: re.Match) -> str:
        nonlocal separators_fixed
        source = registry.by_id(match.group(1))
        quote = clean_quote(match.group(2))
        if source is None or not quote:
            return match.group(0)
        if not quote_in_source(quote, source.text):
            return match.group(0)  # a wrong quote is a problem for the model to fix, not for us to guess at
        canonical = f"[[cite:{source.id}|{quote}]]"
        if match.group(0)[len("[[cite:") + 8] != "|":
            separators_fixed = True
        return canonical

    fixed = CITATION_RE.sub(fix_quote, fixed)
    if separators_fixed:
        repairs.append("rewrote citation separators to |")
    return fixed, repairs
