import os
from contextlib import nullcontext
from dataclasses import dataclass, field, replace

from src.api.trace import RequestTrace
from src.ingestion.extractor import ExtractionError, extract_bytes
from src.providers.base import Provider
from src.providers.router import select_provider
from src.validations.sources import has_source_headers
from src.workflow.reflexion import RunResult, run

@dataclass(frozen=True)
class Clearance:
    """What the asker may see. Passed to tools, never written by the model."""

    level: int

@dataclass(frozen=True)
class Attachment:
    """One file sent with a request. `text` is the body: inline when the client sent text, otherwise
    extracted from `data` by xberg. `error` holds why extraction failed, when it did."""

    filename: str
    content_type: str = ""
    text: str = ""
    data: bytes = b""
    meta: dict = field(default_factory=dict)
    error: str = ""

    @property
    def size(self) -> int:
        return len(self.data) if self.data else len(self.text.encode("utf-8"))

    @property
    def extracted(self) -> bool:
        return bool(self.text.strip())

@dataclass
class Answer:
    result: RunResult
    provider: str
    context: str
    attachments: list[Attachment] = field(default_factory=list)

def _label(
    value: str
) -> str:
    return " ".join(value.replace("[", "").replace("]", "").split()) or "attachment"

def resolve_attachments(
    attachments: list[Attachment]
) -> list[Attachment]:
    # inline text is used as is; raw bytes go through xberg. A file that fails to extract is kept
    # with its error so the caller and the trace can report it, rather than crashing the request.
    resolved = []
    for attachment in attachments:
        if attachment.text.strip() or not attachment.data:
            resolved.append(attachment)
            continue
        try:
            text, meta = extract_bytes(attachment.data, attachment.filename, attachment.content_type)
        except ExtractionError as caught:
            resolved.append(replace(attachment, error=str(caught)))
        else:
            resolved.append(replace(attachment, text=text, meta=meta))
    return resolved

def prepare_context(
    context: str,
    attachments: list[Attachment]
) -> str:
    # inline text becomes a source per file; files with bytes only are held back for the extractor
    inline = [attachment for attachment in attachments if attachment.text.strip()]
    base = (context or "").strip()
    if not inline:
        return base
    blocks = []
    if base:
        blocks.append(base if has_source_headers(base) else f"[context: provided context]\n{base}")
    for attachment in inline:
        blocks.append(f"[file: {_label(attachment.filename)}]\n{attachment.text.strip()}")
    return "\n\n".join(blocks)

def answer_question(
    question: str,
    context: str = "",
    user: Clearance | None = None,
    attachments: list[Attachment] | None = None,
    provider: Provider | None = None,
    trace: RequestTrace | None = None
) -> Answer:
    asked = (question or "").strip()
    if not asked:
        raise ValueError("question is required")
    files = list(attachments or [])
    with (trace.stage("attachments") if trace else nullcontext()):
        files = resolve_attachments(files)
    with (trace.stage("preprocess") if trace else nullcontext()):
        full_context = prepare_context(context, files)
    with (trace.stage("provider") if trace else nullcontext()):
        chosen = provider or select_provider(interactive=False)
    with (trace.stage("workflow") if trace else nullcontext()):
        result = run(chosen, asked, full_context, user=user)
    return Answer(result=result, provider=chosen.name, context=full_context, attachments=files)
