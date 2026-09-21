"""Seed uses an authorized admin API, with no implicit tenancy or overwrites."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from scripts.seed_extract_configuration import seed_configuration

SEED = json.loads((Path(__file__).resolve().parents[2] / 'configurations/seeds/prj-basic-info-drug-registration.json').read_text())


def existing(**changes):
    return {**{k: v for k, v in SEED.items() if k != 'definition'},
        'id': 'c', 'tenant_id': 't', 'project_id': 'p', 'status': 'draft',
        'draft_definition': copy.deepcopy(SEED['definition']), **changes}


def test_creates_only_draft_with_explicit_scope():
    request = Mock(side_effect=[[], {'data': existing()}])
    assert seed_configuration(request, SEED, 't', 'p')['action'] == 'created'
    assert request.call_args.args[0] == 'POST'
    assert request.call_args.args[2]['tenant_id'] == 't'
    assert request.call_args.args[2]['project_id'] == 'p'
    assert all('/publish' not in call.args[1] for call in request.call_args_list)


def test_identical_rerun_does_not_write_or_publish():
    request = Mock(return_value=[existing(status='published')])
    assert seed_configuration(request, SEED, 't', 'p')['action'] == 'unchanged'
    assert request.call_count == 1


def test_conflicting_user_edit_is_not_overwritten():
    request = Mock(return_value=[existing(name='用户修改')])
    with pytest.raises(ValueError, match='不覆盖'):
        seed_configuration(request, SEED, 't', 'p')
    assert request.call_count == 1


def test_empty_scope_fails_before_io():
    request = Mock()
    with pytest.raises(ValueError):
        seed_configuration(request, SEED, '', 'p')
    request.assert_not_called()


def test_foreign_tenant_result_is_not_used():
    request = Mock(side_effect=[[existing(tenant_id='other')], {'data': existing()}])
    assert seed_configuration(request, SEED, 't', 'p')['action'] == 'created'


def test_duplicate_code_is_ambiguous_and_no_write():
    request = Mock(return_value=[existing(), existing(id='c2')])
    with pytest.raises(ValueError, match='多个'):
        seed_configuration(request, SEED, 't', 'p')
    assert request.call_count == 1
