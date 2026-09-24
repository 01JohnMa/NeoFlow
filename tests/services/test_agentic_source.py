import pytest
from services.agentic_source import route_with_agent, AgenticSourceError
from services.parse_result import ParseResult, Page
from services.source_page_index import SourcePage, SourcePageIndex, SourcePageCandidate


def index():
    return SourcePageIndex('h',[SourcePage(1,'text','alpha'),SourcePage(2,'text','beta')],[[1.0,0.0],[0.0,1.0]],'p')

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
