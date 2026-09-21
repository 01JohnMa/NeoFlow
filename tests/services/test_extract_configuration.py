"""Authoring-only regression tests; no database/LLM calls."""
import copy
import json
from pathlib import Path

import pytest

from services.extract_configuration import (
    ExtractConfigurationError,
    draft_fields_definition,
    empty_extract_definition,
    merge_extract_definition,
    validate_extract_definition,
)
from services.extract_schema import validate_value

ROOT = Path(__file__).resolve().parents[2]


def test_empty_new_draft_is_explicit_schema():
    value = empty_extract_definition()
    assert set(value) == {'target', 'data_schema', 'ui'}
    assert validate_extract_definition(value) == value
    assert value['data_schema']['properties'] == {}


@pytest.mark.parametrize('definition', [None, [], {}, {'fields': []}, {'data_schema': None},
    {'data_schema': {'type': 'object'}, 'fields': []},
    {'data_schema': {'type': 'object'}, 'extraction_prompt': 'ignored?'}])
def test_invalid_or_legacy_definition_is_rejected(definition):
    with pytest.raises(ExtractConfigurationError):
        validate_extract_definition(definition)


@pytest.mark.parametrize('target', [None, '', False, 'per_table_row'])
def test_explicit_invalid_target_is_not_defaulted(target):
    with pytest.raises(ExtractConfigurationError):
        validate_extract_definition({**empty_extract_definition(), 'target': target})


def test_raw_execution_subset_is_not_narrowed_to_builder_profile():
    definition = {'data_schema': {'type': 'object', 'properties': {
        'n': {'type': 'integer', 'enum': [1, 2]},
        'value': {'type': ['string', 'null']},
        'nested': {'type': 'object', 'properties': {'list': {'type': 'array', 'items': {'type': 'boolean'}}}},
    }}}
    result = validate_extract_definition(definition)
    assert result == definition and result is not definition
    assert 'target' not in result


def test_ui_json_pointer_escaping_and_distinct_nested_keys():
    definition = empty_extract_definition()
    definition['data_schema']['properties'] = {
        'name': {'type': 'string'},
        'a/~b': {'type': 'array', 'items': {'type': 'object', 'properties': {'name': {'type': 'string'}}}},
    }
    definition['ui'] = {'/properties/name': {'label': '顶层'},
        '/properties/a~1~0b/items/properties/name': {'label': '子字段', 'order': 0}}
    assert validate_extract_definition(definition) == definition
    definition['ui']['/properties/a/~b/name'] = {'label': 'bad'}
    with pytest.raises(ExtractConfigurationError):
        validate_extract_definition(definition)


@pytest.mark.parametrize('metadata', [{'label': None}, {'order': -1}, {'order': True}, {'required': True}])
def test_ui_cannot_change_extraction_semantics(metadata):
    definition = empty_extract_definition()
    definition['data_schema']['properties']['name'] = {'type': 'string'}
    definition['ui'] = {'/properties/name': metadata}
    with pytest.raises(ExtractConfigurationError):
        validate_extract_definition(definition)


def test_schema_replacement_is_not_recursive_merge_and_rejects_stale_ui():
    base = draft_fields_definition([{'field_key': 'old', 'field_type': 'text'}])
    new_schema = {'type': 'object', 'properties': {'new': {'type': 'string'}}}
    with pytest.raises(ExtractConfigurationError):
        merge_extract_definition(base, {'data_schema': new_schema})
    merged = merge_extract_definition(base, {'data_schema': new_schema, 'ui': {}})
    assert 'old' not in merged['data_schema']['properties']
    assert 'old' in base['data_schema']['properties']


def test_ai_proposal_materializes_once_without_persisted_fields_or_example_values():
    fields = [{'field_key': 'date', 'field_label': '日期', 'field_type': 'date', 'sample_value': 'private'}]
    result = draft_fields_definition(fields, '全局规则')
    assert set(result) == {'target', 'data_schema', 'ui'}
    assert result['data_schema']['description'] == '全局规则'
    assert 'private' not in json.dumps(result)
    assert 'required' not in result['data_schema']
    assert result['data_schema']['properties']['date']['format'] == 'date'


def test_ai_duplicate_keys_rejected_before_map_overwrite():
    with pytest.raises(ExtractConfigurationError, match='重复'):
        draft_fields_definition([{'field_key': 'a', 'field_type': 'text'}, {'field_key': 'a', 'field_type': 'number'}])


def test_seed_contract_and_sparse_values():
    payload = json.loads((ROOT / 'configurations/seeds/prj-basic-info-drug-registration.json').read_text())
    definition = validate_extract_definition(payload['definition'])
    schema = definition['data_schema']
    before = copy.deepcopy(schema)
    assert len(schema['properties']) == 38
    assert len(definition['ui']) == 48
    assert sum('enum' in n for n in schema['properties'].values()) == 8
    assert not schema.get('required')
    for key in ('combination_products', 'control_products'):
        node = schema['properties'][key]
        assert node['type'] == 'array'
        assert len(node['items']['properties']) == 5
        assert node['items']['required'] == ['name']
        assert not node['items']['additionalProperties']
    assert validate_value(schema, {}) == []
    sparse = {'planned_subject_count': 0, 'control_products': [{'name': '文档中列明的对照产品'}]}
    assert validate_value(schema, sparse) == []
    assert 'trial_phase' not in sparse and 'name_en' not in sparse['control_products'][0]
    assert validate_value(schema, {'control_products': [{}]})
    assert validate_value(schema, {'trial_phase': 'unknown'})
    assert validate_value(schema, {'planned_start_date': '2026-02-30'})
    assert validate_value(schema, {'planned_start_date': '2026-02'})
    assert validate_value(schema, {'planned_start_date': None})
    assert schema == before
