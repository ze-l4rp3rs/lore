import re
import os
from dataclasses import dataclass, field

import config
from src.validations.citations import CITATION_RE, clean_quote, quote_in_source
from src.validations.sources import SourceRegistry

_LINE_PREFIX = re.compile(r"^\s*(?:#{1,6}\s+|[-*•]\s+|\d+[.)]\s+)?")
_SENTENCE_END = re.compile(r"([.!?][\"')\]*_]*)\s+(?=[^\s\x00])")
_NO_SPLIT_AFTER = {"e.g", "i.e", "vs", "etc", "approx", "mr", "mrs", "ms", "dr", "no", "st"}
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")

# a markdown link whose target is not a URL, e.g. "[TICKET-12](TICKET-12, 2026-08-04)": a fake citation
_FAKE_LINK = re.compile(r"\[[^\]\n]+\]\((?!https?://)[^)\n]*\)")
_REASONING_MARKERS = ("<think", "</think", "<thinking", "</thinking", "Thinking Process:")
# an uncited sentence is fine only when it states a gap, e.g. "The sources do not state a budget."
_GAP_STATEMENT = re.compile(
    r"\b(?:not|no|none|never|nothing|doesn't|don't|isn't|aren't)\b.*\b(?:sources?|records?|context|documents?|mentioned|stated?|documented)\b",
    re.IGNORECASE,
)

@dataclass
class Line:
    prefix: str  # bullet, number or heading marker, kept when the line is rebuilt
    sentences: list[str] = field(default_factory=list)
    gap: bool = False  # sits under the "not in company records" heading: states missing information

@dataclass
class Draft:
    """An answer split into lines and sentences; sentences with content are numbered S1, S2, ..."""
    text: str
    lines: list[Line]
    numbered: dict[int, tuple[int, int]]  # sentence number -> (line index, sentence index)

    def sentence(
        self,
        number: int
    ) -> str:
        line, position = self.numbered[number]
        return self.lines[line].sentences[position]

    def labelled(self) -> str:
        # the layout the verifier sees: every numbered sentence prefixed with [S<n>]
        labels = {place: number for number, place in self.numbered.items()}
        out = []
        for line_index, line in enumerate(self.lines):
            parts = []
            for position, sentence in enumerate(line.sentences):
                number = labels.get((line_index, position))
                parts.append(f"[S{number}] {sentence}" if number else sentence)
            out.append(line.prefix + " ".join(parts))
        return "\n".join(out)

    def without(
        self,
        drop: set[int]
    ) -> str:
        removed = {self.numbered[number] for number in drop if number in self.numbered}
        out = []
        for line_index, line in enumerate(self.lines):
            kept = [s for position, s in enumerate(line.sentences) if (line_index, position) not in removed]
            if line.sentences and not kept:
                continue  # every sentence on this line was removed: drop the bullet too
            out.append(line.prefix + " ".join(kept))
        return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()

def strip_citations(
    text: str
) -> str:
    return re.sub(r"\s+([.,;:!?])", r"\1", CITATION_RE.sub("", text)).strip()

def _split_sentences(
    line: str
) -> list[str]:
    # citation quotes contain periods: hide the tokens while splitting
    tokens: list[str] = []

    def hide(match: re.Match) -> str:
        tokens.append(match.group(0))
        return f"\x00{len(tokens) - 1}\x00"

    hidden = CITATION_RE.sub(hide, line)
    sentences, start = [], 0
    for match in _SENTENCE_END.finditer(hidden):
        word = re.search(r"[\w.]*$", hidden[start:match.start()]).group(0)
        initial = len(word) == 1 and word.isupper()
        if match.group(1)[0] == "." and (word.lower() in _NO_SPLIT_AFTER or initial):
            continue  # "e.g." or an initial, not the end of a sentence
        sentences.append(hidden[start:match.end(1)])
        start = match.end()
    sentences.append(hidden[start:])
    return [_PLACEHOLDER.sub(lambda m: tokens[int(m.group(1))], s).strip() for s in sentences if s.strip()]

def parse_draft(
    text: str
) -> Draft:
    lines: list[Line] = []
    numbered: dict[int, tuple[int, int]] = {}
    in_gaps, gaps_have_items = False, False
    for raw in text.strip().splitlines():
        prefix = _LINE_PREFIX.match(raw).group(0)
        line = Line(prefix=prefix, sentences=_split_sentences(raw[len(prefix):]))
        body = raw[len(prefix):].strip()
        if body.startswith(config.GAPS_HEADING):
            in_gaps, gaps_have_items = True, False
        elif in_gaps and not body:
            in_gaps = in_gaps and not gaps_have_items  # a blank line after the items ends the section
        elif in_gaps and (prefix.lstrip().startswith("#") or _is_heading(body)):
            in_gaps = False
        elif in_gaps:
            line.gap, gaps_have_items = True, True
        for position, sentence in enumerate(line.sentences):
            if re.search(r"\w", strip_citations(sentence)):
                numbered[len(numbered) + 1] = (len(lines), position)
        lines.append(line)
    return Draft(text=text, lines=lines, numbered=numbered)

def _plain_label(
    kinds: set[str]
) -> re.Pattern:
    # "[ticket: TICKET-12, 2026-08-04]" written out instead of a token
    alternatives = "|".join(sorted(re.escape(kind) for kind in kinds | {"source"}))
    return re.compile(r"(?<!\[)\[(?:" + alternatives + r")\s*:[^\]\n]*\](?!\])", re.IGNORECASE)

def _is_heading(
    sentence: str
) -> bool:
    bare = sentence.strip().strip("*_ ").strip()
    return bare.endswith(":") or bool(re.fullmatch(r"\*\*[^*]+\*\*", sentence.strip()))

def _needs_citation(
    sentence: str
) -> bool:
    # headings ("**Status:**"), the gaps line and statements of missing information carry no facts
    if sentence.startswith(config.GAPS_HEADING) or _GAP_STATEMENT.search(sentence):
        return False
    return not _is_heading(sentence)

def mechanical_issues(
    draft: Draft,
    registry: SourceRegistry
) -> dict[int, list[str]]:
    # problems code can prove, per sentence number; quotes have already been through repair_citations
    plain_label = _plain_label({source.kind for source in registry.sources})
    issues: dict[int, list[str]] = {}
    for number in draft.numbered:
        sentence = draft.sentence(number)
        found = []
        for match in CITATION_RE.finditer(sentence):
            source = registry.by_id(match.group(1))
            quote = clean_quote(match.group(2))
            if source is None:
                found.append(f"cites {match.group(1)}, which is not a source id")
            elif not quote:
                if config.REQUIRE_QUOTES:
                    found.append(f"citation of {source.id} has no quote; add the exact words from that source")
            elif not quote_in_source(quote, source.text):
                found.append(f'quote "{quote}" is not in source {source.id}; copy the words exactly or cite the right source')
        rest = CITATION_RE.sub("", sentence)
        in_gap_section = draft.lines[draft.numbered[number][0]].gap  # missing information has nothing to cite
        if rest == sentence and not in_gap_section and _needs_citation(sentence):
            found.append("has no citation; cite the source(s) it is based on (for a calculation or inference, cite every source it uses) or delete it")
        if "cite:" in rest:
            found.append("malformed citation; use [[cite:<id>|<quote>]]")
        if _FAKE_LINK.search(rest) or plain_label.search(rest):
            found.append("source written as plain text; use a [[cite:<id>|<quote>]] token")
        if any(marker in sentence for marker in _REASONING_MARKERS):
            found.append("contains reasoning notes instead of answer text")
        if found:
            issues[number] = found
    return issues
