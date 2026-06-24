"""In-memory screen frame relay store — consent-based JPEG ingest from companion browsers."""

from __future__ import annotations

import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

MAX_FRAME_BYTES = 2_500_000
MAX_SESSIONS = 12
SESSION_TTL_SEC = 300.0
FRAME_STALE_SEC = 30.0


def lan_ip() -> str:
    """Best-effort LAN address for QR / relay URLs."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


@dataclass
class FrameSession:
    session_id: str
    device_address: str | None = None
    label: str = "Relay"
    created_at: float = field(default_factory=time.time)
    last_frame_at: float | None = None
    frame_count: int = 0
    last_width: int | None = None
    last_height: int | None = None
    last_frame: bytes | None = None
    streaming: bool = False

    def to_dict(self) -> dict[str, Any]:
        now = time.time()
        return {
            "sessionId": self.session_id,
            "deviceAddress": self.device_address,
            "label": self.label,
            "createdAt": self.created_at,
            "lastFrameAt": self.last_frame_at,
            "frameCount": self.frame_count,
            "width": self.last_width,
            "height": self.last_height,
            "streaming": self.streaming,
            "live": bool(
                self.last_frame_at and (now - self.last_frame_at) < FRAME_STALE_SEC
            ),
            "ageSec": round(now - self.created_at, 1),
        }


class FrameStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sessions: dict[str, FrameSession] = {}

    def _prune(self) -> None:
        now = time.time()
        stale = [
            sid
            for sid, s in self.sessions.items()
            if (now - s.created_at) > SESSION_TTL_SEC
            and (not s.last_frame_at or (now - s.last_frame_at) > SESSION_TTL_SEC)
        ]
        for sid in stale:
            self.sessions.pop(sid, None)
        if len(self.sessions) > MAX_SESSIONS:
            ordered = sorted(self.sessions.values(), key=lambda s: s.last_frame_at or s.created_at)
            for s in ordered[: len(self.sessions) - MAX_SESSIONS]:
                self.sessions.pop(s.session_id, None)

    def create_session(
        self,
        device_address: str | None = None,
        label: str | None = None,
    ) -> FrameSession:
        sid = secrets.token_urlsafe(10)
        session = FrameSession(
            session_id=sid,
            device_address=device_address,
            label=label or "Screen relay",
        )
        with self.lock:
            self._prune()
            self.sessions[sid] = session
        return session

    def get(self, session_id: str) -> FrameSession | None:
        with self.lock:
            return self.sessions.get(session_id)

    def ingest_frame(
        self,
        session_id: str,
        jpeg: bytes,
        width: int | None = None,
        height: int | None = None,
        device_address: str | None = None,
    ) -> dict[str, Any]:
        if len(jpeg) > MAX_FRAME_BYTES:
            return {"ok": False, "error": "frame too large"}
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return {"ok": False, "error": "unknown session"}
            session.last_frame = jpeg
            session.last_frame_at = time.time()
            session.frame_count += 1
            session.streaming = True
            if width:
                session.last_width = width
            if height:
                session.last_height = height
            if device_address:
                session.device_address = device_address
            return {"ok": True, "frameCount": session.frame_count, "sessionId": session_id}

    def latest_jpeg(self, session_id: str) -> tuple[bytes | None, FrameSession | None]:
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return None, None
            return session.last_frame, session

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            self._prune()
            sessions = [s.to_dict() for s in self.sessions.values()]
        live = sum(1 for s in sessions if s.get("live"))
        return {
            "sessionCount": len(sessions),
            "liveCount": live,
            "sessions": sorted(sessions, key=lambda s: s.get("lastFrameAt") or 0, reverse=True),
        }


FRAME_STORE = FrameStore()


def relay_urls(session_id: str, port: int, bind_all: bool) -> dict[str, str]:
    host = lan_ip() if bind_all else "127.0.0.1"
    base = f"http://{host}:{port}"
    return {
        "relayPage": f"{base}/relay?session={session_id}",
        "latestFrame": f"{base}/api/screen/frame/latest?session={session_id}",
        "ingest": f"{base}/api/screen/frame",
    }
