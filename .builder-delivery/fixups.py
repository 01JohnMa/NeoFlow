"""Update SDK regression assertions for the intentional schema-first draft contract."""
import ast
import hashlib
from pathlib import Path

path = Path('tests/test_sdk/test_orchestrator.py')
raw = path.read_bytes()
assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == 'c96c0ba060ffbf8e9200ff63ad09e7bdc3bb3ed8'
s = raw.decode()

def replace_function(name, replacement):
    global s
    nodes = [n for n in ast.parse(s).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(nodes) == 1, name
    n = nodes[0]
    start = min([n.lineno] + [d.lineno for d in n.decorator_list]) - 1
    lines = s.splitlines(keepends=True)
    s = ''.join(lines[:start]) + replacement.strip() + '\n' + ''.join(lines[n.end_lineno:])

s = s.replace('from services.configuration_service import normalize_definition\n', 'from unittest.mock import AsyncMock\n\nfrom services.extract_configuration import validate_extract_definition\n')
replace_function('test_commit_creates_and_publishes_configuration', '''
@pytest.mark.asyncio
async def test_commit_creates_schema_draft_without_publishing(monkeypatch):
    create = AsyncMock(return_value={"id": "config-1", "status": "draft", "tenant_id": "tenant-1"})
    publish = AsyncMock()
    monkeypatch.setattr("sdk.agents.orchestrator.configuration_service.create_configuration", create)
    monkeypatch.setattr("sdk.agents.orchestrator.configuration_service.publish_configuration", publish)
    session = _build_session(
        parse_mode="vlm",
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="出货单", template_code="shipment_report",
            fields=[{
                "field_key": "order_no", "field_label": "订单号", "field_type": "text",
                "extraction_hint": "从订单号标签后提取", "sample_value": "NOZS0311046",
            }],
        ),
        prompt="仅从订单号标签后的原文提取，有歧义时省略。",
    )
    result = await SDKOrchestrator().commit(session)
    create.assert_awaited_once()
    publish.assert_not_awaited()
    payload = create.await_args.args[0]
    assert create.await_args.kwargs["created_by"] == session.user_id
    assert payload["tenant_id"] == "tenant-1"
    assert payload["name"] == "出货单"
    assert payload["code"] == "shipment_report"
    assert payload["type"] == "extract"
    definition = validate_extract_definition(payload["definition"])
    assert set(definition) == {"data_schema", "target", "ui"}
    assert definition["target"] == "per_doc"
    assert definition["data_schema"] == {
        "type": "object", "additionalProperties": False,
        "description": session.prompt,
        "properties": {"order_no": {"type": "string", "description": "从订单号标签后提取"}},
    }
    assert definition["ui"] == {"/properties/order_no": {"label": "订单号", "order": 0}}
    assert "NOZS0311046" not in str(definition)
    assert result.configuration_id == "config-1"
    assert result.tenant_id == "tenant-1"
    assert result.status == "draft"
    assert result.revision_id is None and result.revision_number is None
    assert result.field_count == 1
    assert session.state == SDKSessionState.COMMITTED
''')
replace_function('test_commit_uses_fallback_prompt_when_missing', '''
@pytest.mark.asyncio
async def test_commit_uses_fallback_schema_description_when_missing(monkeypatch):
    create = AsyncMock(return_value={"id": "config-2"})
    publish = AsyncMock()
    monkeypatch.setattr("sdk.agents.orchestrator.configuration_service.create_configuration", create)
    monkeypatch.setattr("sdk.agents.orchestrator.configuration_service.publish_configuration", publish)
    session = _build_session(
        id="session-2", user_id="user-1", state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="检测报告", template_code="inspection_report",
            fields=[{"field_key": "sample_name", "field_label": "样品名称"}],
        ),
    )
    result = await SDKOrchestrator().commit(session)
    create.assert_awaited_once()
    publish.assert_not_awaited()
    definition = validate_extract_definition(create.await_args.args[0]["definition"])
    assert set(definition) == {"data_schema", "target", "ui"}
    assert definition["data_schema"]["properties"]["sample_name"]["type"] == "string"
    description = definition["data_schema"]["description"]
    assert "可选字段省略" in description
    assert "{markdown}" not in description
    assert result.status == "draft"
    assert result.revision_id is None and result.revision_number is None
''')
assert s.count('assert "解析文本" in result') == 1
s = s.replace('assert "解析文本" in result', 'assert "可选字段省略" in result')
assert s.count('assert "{markdown}" in result') == 1
s = s.replace('assert "{markdown}" in result', 'assert "{markdown}" not in result')
s = s.replace('请提取字段：sample_name\\n{markdown}', '仅依据样品名称标签后的原文提取 sample_name')
ast.parse(s)
path.write_text(s)
print('Updated SDK tests: draft-only persistence, schema guidance, no legacy prompt wrappers.')
