import pytest
from services.agentic_source import (
    FieldCompletion,
    assess_field_completion,
    incomplete_field_queries,
    route_with_agent,
    AgenticSourceError,
)
from services.parse_result import ParseResult, Page
from services.source_page_index import SourcePage, SourcePageIndex, SourcePageCandidate


def index():
    return SourcePageIndex('h',[SourcePage(1,'text','alpha'),SourcePage(2,'text','beta')],[[1.0,0.0],[0.0,1.0]],'p')


def test_field_completion_is_generic_and_evidence_bound():
    schema = {"type": "string", "enum": ["A", "B"]}
    assert assess_field_completion(schema, "", evidence_pages=[1]).status == "unresolved"
    assert assess_field_completion(schema, "A").status == "unresolved"
    assert assess_field_completion(schema, "C", evidence_pages=[1]).status == "conflict"
    assert assess_field_completion(schema, "A", evidence_pages=[1]).status == "complete"


def test_field_completion_detects_list_gaps_and_products():
    list_schema = {"type": "string"}
    result = assess_field_completion(list_schema, "1）a\n3）c", evidence_pages=[2])
    assert result == FieldCompletion("incomplete", ("numbered_list_gap",))
    product_schema = {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}}}}
    assert assess_field_completion(product_schema, [{}], evidence_pages=[2]).status == "incomplete"


def test_incomplete_queries_only_include_followups():
    schema = {"properties": {"a": {"description": "Alpha"}, "b": {"description": "Beta"}}}
    queries = incomplete_field_queries(schema, {"a": FieldCompletion("incomplete"), "b": FieldCompletion("complete")})
    assert queries == ["a Alpha"]

@pytest.mark.asyncio
async def test_agent_tools_search_parse_and_merge(monkeypatch):
    async def retrieve(idx, queries, request_gate=None):
        return {k:[SourcePageCandidate(1, .9, ['text'])] for k in queries}
    monkeypatch.setattr('services.agentic_source.retrieve_source_pages', retrieve)
    parsed = []
    async def parse(pages):
        parsed.append(pages)
        return ParseResult(pages=[Page(p, 10, 10, markdown=f'p{p}') for p in pages])
    async def factory(**kw):
        return None
    class Agent:
        async def arun(self, prompt):
            await self.tools['search_pages'](['field'])
            await self.tools['parse_pages']([1, 2])
        def __init__(self, tools): self.tools=tools
    def make(**kw): return Agent(kw['tools'])
    out = await route_with_agent(index(), {'type':'object'}, parse, agent_factory=make)
    assert [p.page_no for p in out.parse_result.pages] == [1,2]
    assert parsed == [[1,2]]
    assert out.stats.searches == 1

@pytest.mark.asyncio
async def test_requires_real_parse():
    class Agent:
        async def arun(self, prompt): return None
    with pytest.raises(AgenticSourceError, match='no_parse'):
        await route_with_agent(index(), {}, lambda p: ParseResult(), agent_factory=lambda **kw: Agent())


@pytest.mark.asyncio
async def test_agent_factory_builds_real_llamaindex_tools_for_field_state_schema(monkeypatch):
    """Keep the LlamaIndex FunctionTool boundary compatible with JSON schemas.

    ``search_incomplete_fields`` is intentionally typed as a plain dict: the
    installed LlamaIndex/Pydantic stack must be able to construct its tool
    schema without resolving a deferred ``Mapping`` annotation.
    """
    from llama_index.core.tools import FunctionTool

    captured = {}

    async def retrieve(idx, queries, request_gate=None):
        return {key: [SourcePageCandidate(1, 0.9, ["text"])] for key in queries}

    monkeypatch.setattr("services.agentic_source.retrieve_source_pages", retrieve)

    class Agent:
        async def arun(self, prompt):
            # Construction (rather than a provider call) is the regression
            # boundary: this exercises the actual FunctionTool JSON-schema path.
            incomplete = captured["tools"]["search_incomplete_fields"]
            params = incomplete.metadata.get_parameters_dict()
            assert params["properties"]["field_states"]["type"] == "object"
            assert params["properties"]["field_states"].get("additionalProperties") is True
            await captured["raw"]["search_incomplete_fields"]({})
            await captured["raw"]["parse_pages"]([1])

    def make(**kw):
        captured["raw"] = kw["tools"]
        captured["tools"] = {
            name: FunctionTool.from_defaults(async_fn=fn, name=name)
            for name, fn in kw["tools"].items()
        }
        # Ensure all nested tools are schema-constructible, as production's
        # FunctionAgent construction does before any model request.
        assert set(captured["tools"]) == {"search_pages", "search_incomplete_fields", "parse_pages"}
        return Agent()

    async def parse(pages):
        return ParseResult(pages=[Page(p, 10, 10, markdown=f"p{p}") for p in pages])

    out = await route_with_agent(
        index(),
        {"properties": {"field": {"description": "Alpha"}}},
        parse,
        agent_factory=make,
    )
    assert [p.page_no for p in out.parse_result.pages] == [1]
