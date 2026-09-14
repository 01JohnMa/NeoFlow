"""In-memory SDK session store with TTL cleanup."""

import time
from typing import Callable, Dict, Optional
from uuid import uuid4

from sdk.models import SDKSession, SDKSessionState


class SDKSessionStore:
    def __init__(self, ttl_seconds: int = 3600, now: Callable[[], float] = time.time):
        self.ttl_seconds = ttl_seconds
        self._now = now
        self._sessions: Dict[str, SDKSession] = {}

    def create(
        self,
        *,
        file_name: str,
        file_path: str,
        tenant_id: str,
        document_id: str,
        parse_job_id: str,
        session_id: str | None = None,
        parse_mode: str = "pipeline",
        state: SDKSessionState = SDKSessionState.PARSING,
        excel_template_file_name: str | None = None,
        excel_template_path: str | None = None,
        excel_placeholders=None,
        user_id: str,
    ) -> SDKSession:
        self.cleanup()
        now = self._now()
        session = SDKSession(
            id=session_id or str(uuid4()),
            file_name=file_name,
            file_path=file_path,
            tenant_id=tenant_id,
            document_id=document_id,
            parse_job_id=parse_job_id,
            parse_mode=parse_mode,
            excel_template_file_name=excel_template_file_name,
            excel_template_path=excel_template_path,
            excel_placeholders=excel_placeholders or [],
            user_id=user_id,
            state=state,
            created_at=now,
            updated_at=now,
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Optional[SDKSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        if self._is_expired(session):
            self._sessions.pop(session_id, None)
            return None
        return session

    def save(self, session: SDKSession) -> SDKSession:
        session.updated_at = self._now()
        self._sessions[session.id] = session
        return session

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def cleanup(self) -> None:
        expired_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if self._is_expired(session)
        ]
        for session_id in expired_ids:
            self._sessions.pop(session_id, None)

    def _is_expired(self, session: SDKSession) -> bool:
        return self._now() - session.updated_at > self.ttl_seconds


session_store = SDKSessionStore()
