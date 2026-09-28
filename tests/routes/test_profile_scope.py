"""Profile edits cannot choose a tenant; scope belongs to the upstream platform."""

from unittest.mock import AsyncMock, patch

from tests.conftest import TENANT_ID, USER_ID


def test_profile_read_preserves_authenticated_scope(client):
    response = client.get('/api/tenants/me/profile')

    assert response.status_code == 200
    assert response.json()['tenant_id'] == TENANT_ID


def test_profile_edit_rejects_tenant_selection(client):
    response = client.put('/api/tenants/me/profile', json={'tenant_id': TENANT_ID})

    assert response.status_code == 422


def test_profile_edit_only_updates_display_name(client):
    with patch('api.routes.tenants.tenant_service.update_user_profile', new_callable=AsyncMock) as update:
        update.return_value = {'id': USER_ID, 'tenant_id': TENANT_ID, 'display_name': 'Operator'}
        response = client.put('/api/tenants/me/profile', json={'display_name': 'Operator'})

    assert response.status_code == 200
    update.assert_awaited_once_with(user_id=USER_ID, display_name='Operator')


def test_tenant_discovery_routes_are_removed(client):
    assert client.get('/api/tenants').status_code == 404
    assert client.get(f'/api/tenants/{TENANT_ID}').status_code == 404
