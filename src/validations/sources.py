import re
import secrets
from dataclasses import dataclass, field

# "[chat: #team-channel, 2026-06-09]" on its own line starts a new source in a context file
_SOURCE_HEADER = re.compile(r"^\[(?P<kind>[A-Za-z_]+):\s*(?P<label>[^\]]+)\]\s*$", re.MULTILINE)
_TRAILING_DATE = re.compile(r"^(?P<label>.*?),\s*(?P<date>\d{4}-\d{2}-\d{2})$")

# our own structural tags; retrieved text must never be able to open or close them
_STRUCTURAL_TAG = re.compile(r"<(/?\s*(?:context|source|question)\b)", re.IGNORECASE)


@dataclass(frozen=True)
class Evidence:
    """One citable piece of a tool result. For the graph this is a Chunk: its text, plus the
    metadata of the Document it belongs to (shown to the user in the source list).

    A tool that returns Evidence (or a list of it) gets one citable source per item;
    any other return value becomes a single source holding the whole result.
    """
    kind: str  # document type: doc, chat, ticket, email, ...
    label: str  # document title, channel, ticket key, ...
    text: str  # the exact text quotes are checked against
    date: str = ""  # ISO date of the document or message
    url: str = ""  # link or path that opens the original document
    ref: str = ""  # stable id in the store (chunk id); the same ref twice maps to the same citation id
    meta: dict = field(default_factory=dict)  # author, company, ...


@dataclass(frozen=True)
class Note:
    """A message about a tool result (for example "more rows matched"). The model reads it with the
    result, but it is never a source, so it can never be cited."""
    text: str


@dataclass(frozen=True)
class Source:
    id: str  # per-run random id the model cites
    kind: str
    label: str
    text: str
    date: str = ""
    url: str = ""
    ref: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class SourceRegistry:
    sources: list[Source] = field(default_factory=list)
    _by_id: dict[str, Source] = field(default_factory=dict, repr=False)
    _by_ref: dict[str, Source] = field(default_factory=dict, repr=False)

    def add(
        self,
        evidence: Evidence
    ) -> Source:
        if evidence.ref and evidence.ref in self._by_ref:
            return self._by_ref[evidence.ref]
        # random per run so untrusted content can never forge a real citation id
        source_id = secrets.token_hex(4)
        while source_id in self._by_id:
            source_id = secrets.token_hex(4)
        source = Source(
            id=source_id,
            kind=evidence.kind,
            label=evidence.label,
            text=evidence.text,
            date=evidence.date,
            url=evidence.url,
            ref=evidence.ref,
            meta=dict(evidence.meta),
        )
        self.sources.append(source)
        self._by_id[source.id] = source
        if source.ref:
            self._by_ref[source.ref] = source
        return source

    def by_id(
        self,
        source_id: str
    ) -> Source | None:
        return self._by_id.get(source_id)


def has_source_headers(
    text: str
) -> bool:
    # True when the text already uses "[kind: label]" record headers and splits into several sources
    return _SOURCE_HEADER.search(text) is not None


def build_registry(
    context: str
) -> SourceRegistry:
    registry = SourceRegistry()
    text = context.strip()
    if not text:
        return registry

    headers = list(_SOURCE_HEADER.finditer(text))
    if not headers:
        registry.add(Evidence(kind="context", label="provided context", text=text))
        return registry

    for position, header in enumerate(headers):
        end = headers[position + 1].start() if position + 1 < len(headers) else len(text)
        label, date = header.group("label").strip(), ""
        dated = _TRAILING_DATE.match(label)
        if dated:
            label, date = dated.group("label").strip(), dated.group("date")
        registry.add(Evidence(
            kind=header.group("kind").lower(),
            label=label,
            text=text[header.end():end].strip(),
            date=date,
        ))
    return registry


def _neutralize(
    text: str
) -> str:
    # "</source>" in retrieved text becomes "&lt;/source>", so it can't end the block early
    return _STRUCTURAL_TAG.sub(r"&lt;\1", text)


def _attribute(
    value: str
) -> str:
    # values sit inside an attribute: no quotes, angle brackets, or line breaks
    return " ".join(value.replace('"', "'").replace("<", "").replace(">", "").split())


def render_sources(
    sources: list[Source]
) -> str:
    lines = []
    for source in sources:
        attributes = f'id="{source.id}" type="{_attribute(source.kind)}" label="{_attribute(source.label)}"'
        if source.date:
            attributes += f' date="{_attribute(source.date)}"'
        lines.append(f"<source {attributes}>")
        lines.append(_neutralize(source.text))
        lines.append("</source>")
    return "\n".join(lines)


def render_context(
    registry: SourceRegistry
) -> str:
    body = render_sources(registry.sources) if registry.sources else "(none yet; use your tools to find sources)"
    return f"<context>\n{body}\n</context>"
