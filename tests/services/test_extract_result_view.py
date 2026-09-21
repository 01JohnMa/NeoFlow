"""Pinned display contracts only; no reads of current configurations."""
import copy
from unittest.mock import AsyncMock

import pytest

from services.extract_result_view import resolve_result_view
from services.extract_schema import schema_hash

SCHEMA = {'type': 'object', 'description': 'not for result viewers', 'properties': {
    'n': {'type': 'number', 'description': 'private extraction instructions'},
}, 'additionalProperties': False}


def snapshot():
    return {'job_id': 'j', 'tenant_id': 't', 'execution_spec': {
        'capability': 'extract', 'spec_version': '1',
        'effective_params': {'data_schema': copy.deepcopy(SCHEMA), 'target': 'per_page'},
    }, 'configuration_revision_id': None}


def row():
    return {'job_id': 'j', 'tenant_id': 't', 'config_revision_id': None,
            'data': [{'n': 0}], 'engine': {'schema_hash': schema_hash(SCHEMA)}}


@pytest.mark.asyncio
async def test_snapshot_never_reads_revision_or_latest_configuration():
    job, result, loader = snapshot(), row(), AsyncMock()
    before = copy.deepcopy((job, result))
    view = await resolve_result_view(job, result, loader)
    assert view['status'] == 'available' and view['origin'] == 'execution_spec'
    assert view['target'] == 'per_page' and view['ui'] == {}
    assert 'description' not in view['schema']
    assert 'description' not in view['schema']['properties']['n']
    loader.assert_not_awaited()
    assert (job, result) == before


@pytest.mark.asyncio
async def test_published_uses_exact_pinned_revision_and_labels():
    job, result = snapshot(), row()
    job.update(execution_spec=None, configuration_revision_id='r-old')
    result['config_revision_id'] = 'r-old'
    loader = AsyncMock(return_value={'id': 'r-old', 'definition': {
        'data_schema': SCHEMA, 'ui': {'/properties/n': {'label': '旧标签', 'order': 0}},
    }})
    view = await resolve_result_view(job, result, loader)
    loader.assert_awaited_once_with('r-old')
    assert view['origin'] == 'revision'
    assert view['ui']['/properties/n']['label'] == '旧标签'


@pytest.mark.asyncio
@pytest.mark.parametrize('change,reason', [({'job_id': 'other'}, 'job_mismatch'),
    ({'tenant_id': 'other'}, 'tenant_mismatch'),
    ({'engine': {'schema_hash': 'changed'}}, 'schema_hash_mismatch'),
    ({'config_revision_id': 'unexpected'}, 'definition_mismatch')])
async def test_mismatch_is_not_hidden_by_using_latest_schema(change, reason):
    result = {**row(), **change}
    before = copy.deepcopy(result)
    view = await resolve_result_view(snapshot(), result, AsyncMock())
    assert view == {'status': 'unavailable', 'reason': reason}
    assert result == before


@pytest.mark.asyncio
async def test_fields_only_snapshot_has_no_conversion():
    job = snapshot()
    job['execution_spec']['effective_params'] = {'fields': [{'field_key': 'n', 'field_type': 'number'}]}
    assert (await resolve_result_view(job, row(), AsyncMock()))['status'] == 'unavailable'


@pytest.mark.asyncio
async def test_missing_revision_does_not_fall_back_to_any_other_definition():
    job, result = snapshot(), row()
    job.update(execution_spec=None, configuration_revision_id='gone')
    result['config_revision_id'] = 'gone'
    loader = AsyncMock(return_value=None)
    assert (await resolve_result_view(job, result, loader))['reason'] == 'revision_unavailable'
    loader.assert_awaited_once_with('gone')
