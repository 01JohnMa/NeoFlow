from sdk.models import SDKSessionState
from sdk.session import SDKSessionStore


def test_session_store_expires_old_sessions(monkeypatch):
    now = {"value": 1000.0}
    store = SDKSessionStore(ttl_seconds=10, now=lambda: now["value"])

    session = store.create(
        file_name="report.pdf",
        file_path="/tmp/report.pdf",
        tenant_id="tenant-1",
        template_name="检测报告",
        template_code="inspection_report",
        document_id="doc-1",
        parse_job_id="job-1",
        user_id="user-1",
    )

    assert store.get(session.id).state == SDKSessionState.PARSING

    now["value"] = 1011.0

    assert store.get(session.id) is None


def test_session_store_delete_removes_session():
    store = SDKSessionStore(ttl_seconds=10)
    session = store.create(
        file_name="report.pdf",
        file_path="/tmp/report.pdf",
        tenant_id="tenant-1",
        template_name="检测报告",
        template_code="inspection_report",
        document_id="doc-1",
        parse_job_id="job-1",
        user_id="user-1",
    )

    assert store.delete(session.id) is True
    assert store.get(session.id) is None
