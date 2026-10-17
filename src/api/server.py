import base64
import binascii
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

import config
from src.api.response import build_response
from src.api.service import Attachment, Clearance, answer_question
from src.api.trace import RequestTrace

class AttachmentIn(BaseModel):
    filename: str = Field(min_length=1)
    content_type: str | None = None
    text: str | None = None
    data_base64: str | None = None

    @model_validator(mode="after")
    def exactly_one_payload(self) -> "AttachmentIn":
        if (self.text is None) == (self.data_base64 is None):
            raise ValueError("exactly one of 'text' or 'data_base64' is required")
        return self

class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    context: str = ""
    clearance_level: int = Field(default=config.MIN_CLEARANCE_LEVEL, ge=config.MIN_CLEARANCE_LEVEL, le=config.MAX_CLEARANCE_LEVEL)
    attachments: list[AttachmentIn] = Field(default_factory=list)

def _decode_attachment(item: AttachmentIn) -> Attachment:
    data = b""
    if item.data_base64 is not None:
        try:
            data = base64.b64decode(item.data_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, f"attachment {item.filename!r} is not valid base64")
    attachment = Attachment(
        filename=item.filename,
        content_type=item.content_type or "",
        text=item.text or "",
        data=data,
    )
    if attachment.size > config.MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, f"attachment {item.filename!r} exceeds {config.MAX_ATTACHMENT_BYTES} bytes")
    return attachment

def _build_attachments(items: list[AttachmentIn]) -> list[Attachment]:
    if len(items) > config.MAX_ATTACHMENTS:
        raise HTTPException(413, f"at most {config.MAX_ATTACHMENTS} attachments per request")
    attachments = [_decode_attachment(item) for item in items]
    total = sum(attachment.size for attachment in attachments)
    if total > config.MAX_TOTAL_ATTACHMENT_BYTES:
        raise HTTPException(413, f"attachments exceed {config.MAX_TOTAL_ATTACHMENT_BYTES} bytes in total")
    return attachments

def _attachment_trace(attachments: list[Attachment]) -> list[dict[str, Any]]:
    return [
        {
            "filename": attachment.filename,
            "contentType": attachment.content_type,
            "bytes": attachment.size,
            "extracted": attachment.extracted,
            "error": attachment.error,
            "meta": attachment.meta,
        }
        for attachment in attachments
    ]

def _failure(
    trace: RequestTrace,
    status_code: int,
    detail: str
) -> JSONResponse:
    trace.finish("error")
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "trace": trace.to_dict()},
        headers={"X-Request-ID": trace.id},
    )

def create_app() -> FastAPI:
    app = FastAPI(title="Company Brain API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/ask")
    def ask(payload: AskRequest, request: Request, response: Response) -> dict[str, Any]:
        trace = RequestTrace.start(id=request.headers.get("X-Request-ID"))
        response.headers["X-Request-ID"] = trace.id
        try:
            with trace.stage("validate"):
                attachments = _build_attachments(payload.attachments)
                user = Clearance(level=payload.clearance_level)
                trace.clearance_level = user.level
            answer = answer_question(
                question=payload.question,
                context=payload.context,
                user=user,
                attachments=attachments,
                trace=trace,
            )
            trace.provider = answer.provider
            trace.log = answer.result.log
            trace.attachments = _attachment_trace(answer.attachments)
            with trace.stage("response"):
                built = build_response(answer.result)
            trace.finish("ok")
            built["metadata"]["trace"] = trace.to_dict()
            return built
        except HTTPException as caught:
            return _failure(trace, caught.status_code, str(caught.detail))
        except ValueError as caught:
            return _failure(trace, 400, str(caught))
        except RuntimeError as caught:
            return _failure(trace, 503, str(caught))
        except Exception as caught:
            return _failure(trace, 500, f"{type(caught).__name__}: {caught}")

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("API_HOST", config.API_HOST),
        port=int(os.getenv("API_PORT", config.API_PORT)),
        reload=os.getenv("API_DEBUG", str(config.API_DEBUG)).lower() in {"1", "true", "yes"},
    )
