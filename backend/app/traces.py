from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.models import TraceRecord


class TraceStore:
    def __init__(self) -> None:
        self._records: dict[str, TraceRecord] = {}
        self._lock = Lock()

    def put(self, record: TraceRecord) -> None:
        with self._lock:
            self._records[record.trace_id] = record

    def get(self, trace_id: str) -> TraceRecord | None:
        with self._lock:
            return self._records.get(trace_id)


def log_event(event: str, **data: Any) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **data,
    }


trace_store = TraceStore()
