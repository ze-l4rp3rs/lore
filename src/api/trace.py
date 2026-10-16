import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator


def _ms(
    started: float
) -> int:
    return int((time.perf_counter() - started) * 1000)


@dataclass
class RequestTrace:
    """The record of one API request: what was attached, every stage and how long it took."""

    id: str
    received_at: str
    started: float = field(default_factory=time.perf_counter)
    stages: list[dict[str, Any]] = field(default_factory=list)
    clearance_level: int | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    provider: str = ""
    log: str = ""
    status: str = "pending"
    duration_ms: int = 0

    @classmethod
    def start(
        cls,
        id: str | None = None
    ) -> "RequestTrace":
        now = datetime.now(timezone.utc)
        return cls(id=id or uuid.uuid4().hex, received_at=now.isoformat().replace("+00:00", "Z"))

    @contextmanager
    def stage(
        self,
        name: str
    ) -> Iterator[None]:
        began = time.perf_counter()
        try:
            yield
        finally:
            self.stages.append({"name": name, "durationMs": _ms(began)})

    def finish(
        self,
        status: str = "ok"
    ) -> "RequestTrace":
        self.status = status
        self.duration_ms = _ms(self.started)
        return self

    def to_dict(
        self
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "receivedAt": self.received_at,
            "status": self.status,
            "clearanceLevel": self.clearance_level,
            "attachments": self.attachments,
            "provider": self.provider,
            "log": self.log,
            "stages": self.stages,
            "totalDurationMs": self.duration_ms or _ms(self.started),
        }
