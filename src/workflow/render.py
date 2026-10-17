import re
import os
from datetime import date

from src.validations import CITATION_RE, Source, SourceRegistry, clean_quote

# source type -> display name
SOURCE_TYPES = {
    "doc": "Document",
    "document": "Document",
    "chat": "Chat",
    "message": "Chat",
    "ticket": "Ticket",
    "email": "Email",
    "meeting": "Meeting",
    "tool": "System",
    "query_result": "Graph result",
    "slackmessage": "Chat",
    "person": "Person",
    "team": "Team",
    "project": "Project",
    "decision": "Decision",
}

def friendly_date(
    value: str
) -> str:
    # "2026-06-09" -> "9 Jun 2026"; anything else is shown as given
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return value
    return f"{parsed.day} {parsed.strftime('%b %Y')}"

def number_citations(
    text: str,
    registry: SourceRegistry
) -> tuple[str, list[dict]]:
    # tokens become [1], [2]... in order of first use; returns the body and the cited sources
    numbers: dict[str, int] = {}
    quotes: dict[str, list[str]] = {}
    cited_sources: dict[str, Source] = {}

    def replace(match: re.Match) -> str:
        source = registry.by_id(match.group(1))
        if source is None:
            return ""  # never reached for a checked draft; don't show a broken marker
        number = numbers.setdefault(source.id, len(numbers) + 1)
        cited_sources[source.id] = source
        quote = clean_quote(match.group(2))
        if quote and quote not in quotes.setdefault(source.id, []):
            quotes[source.id].append(quote)
        return f"[{number}]"

    body = CITATION_RE.sub(replace, text)
    body = re.sub(r"[ \t]+(\[\d+\])", r"\1", body)  # "claim [1]" -> "claim[1]"
    body = re.sub(r"(\[\d+\])(?:\1)+", r"\1", body)  # "[1][1]" -> "[1]"
    body = re.sub(r"((?:\[\d+\])+)([.,;:])", r"\2\1", body)  # "claim[1]." -> "claim.[1]"

    cited = []
    for source_id, number in numbers.items():
        source = cited_sources[source_id]
        cited.append({
            "number": number,
            "id": source_id,
            "type": source.kind,
            "label": source.label,
            "date": source.date,
            "url": source.url,
            "ref": source.ref,
            "meta": source.meta,
            "quotes": quotes.get(source_id, []),
        })
    return body.strip(), cited

def source_line(
    source: dict
) -> str:
    name = SOURCE_TYPES.get(source["type"], source["type"].title())
    label = f"[{source['label']}]({source['url']})" if source["url"] else source["label"]
    parts = [name, label] + ([friendly_date(source["date"])] if source["date"] else [])
    lines = [f"[{source['number']}] " + " · ".join(parts)]
    # a quote already contained in a longer quote from the same source adds nothing
    quotes = [q for q in source["quotes"] if not any(q != other and q in other for other in source["quotes"])]
    lines += [f"> “{quote}”" for quote in quotes]
    return "\n".join(lines)

def render_markdown(
    body: str,
    sources: list[dict],
    unverified: list[dict],
    premise: list[str],
    missing: list[str],
    checked: bool
) -> str:
    out = []
    if not checked:
        out += ["⚠ **This answer could not be fact-checked.** Check the quoted sources before relying on it.", ""]
    out.append(body)
    if sources:
        out += ["", "---", "**Sources**", ""]
        out.append("\n\n".join(source_line(source) for source in sources))
    if unverified or premise:
        out += ["", "---", "⚠ **Couldn't verify.** These were left out because the records don't clearly support them:", ""]
        out += [f"- “{item['claim']}” ({item['reason']})" for item in unverified]
        out += [f"- Your question assumes something the records don't support: {item}" for item in premise]
    if missing:
        out += ["", "**The records don't answer:** " + " ".join(missing)]
    return "\n".join(out).strip()
