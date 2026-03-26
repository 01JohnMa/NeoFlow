import pytest
from unittest.mock import MagicMock, patch

from api.jobs import (
    create_job,
    update_job,
    get_job,
    update_batch_item,
    find_job_by_dedupe_key,
    record_feishu_push,
    has_feishu_push_record,
)


def _mock_result(data=None, count=None):
    result = MagicMock()
    result.data = data if data is not None else []
    result.count = count
    return result


def _mock_chain(result=None):
    chain = MagicMock()
    for method in (
        'select', 'eq', 'order', 'limit', 'insert', 'update', 'upsert', 'delete', 'or_'
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = result or _mock_result()
    return chain


class TestJobService:
    @pytest.mark.asyncio
    async def test_create_job_persists_batch_job_with_queued_status(self):
        with patch('api.jobs.supabase_service') as mock_svc:
            insert_result = _mock_result([{'job_id': 'job-123', 'status': 'queued'}])
            mock_svc.client.table.return_value = _mock_chain(insert_result)

            job_id = await create_job(
                batch_items=[{'index': 0, 'type': 'single', 'document_ids': ['doc-1'], 'status': 'queued'}],
                job_type='batch',
                created_by='user-1',
                dedupe_key='dedupe-1',
            )

        assert job_id == 'job-123'
        table = mock_svc.client.table.return_value
        table.insert.assert_called_once()
        payload = table.insert.call_args.args[0]
        assert payload['job_type'] == 'batch'
        assert payload['status'] == 'queued'
        assert payload['stage'] == 'queued'
        assert payload['created_by'] == 'user-1'
        assert payload['dedupe_key'] == 'dedupe-1'
        assert payload['total'] == 1

    @pytest.mark.asyncio
    async def test_update_job_moves_status_from_stage(self):
        with patch('api.jobs.supabase_service') as mock_svc:
            mock_svc.client.table.return_value = _mock_chain(_mock_result([{'job_id': 'job-1'}]))

            await update_job('job-1', 'ocr')

        payload = mock_svc.client.table.return_value.update.call_args.args[0]
        assert payload['stage'] == 'ocr'
        assert payload['status'] == 'processing'
        assert payload['progress'] == 30

    @pytest.mark.asyncio
    async def test_update_batch_item_recalculates_progress_and_completion(self):
        with patch('api.jobs.supabase_service') as mock_svc:
            select_chain = _mock_chain(_mock_result([{
                'job_id': 'job-1',
                'items': [
                    {'index': 0, 'status': 'queued', 'document_ids': []},
                    {'index': 1, 'status': 'queued', 'document_ids': []},
                ],
                'document_ids': [],
                'total': 2,
            }]))
            update_chain = _mock_chain(_mock_result([{'job_id': 'job-1'}]))
            mock_svc.client.table.side_effect = [select_chain, update_chain]

            await update_batch_item('job-1', 0, 'completed', document_ids=['doc-1'])

        update_payload = update_chain.update.call_args.args[0]
        assert update_payload['completed_count'] == 1
        assert update_payload['progress'] == 50
        assert update_payload['status'] == 'processing'
        assert update_payload['document_ids'] == ['doc-1']
        assert update_payload['items'][0]['status'] == 'completed'

    @pytest.mark.asyncio
    async def test_get_job_returns_persisted_job(self):
        with patch('api.jobs.supabase_service') as mock_svc:
            mock_svc.client.table.return_value = _mock_chain(_mock_result([{
                'job_id': 'job-1',
                'status': 'queued',
                'stage': 'queued',
                'progress': 0,
            }]))

            job = await get_job('job-1')

        assert job is not None
        assert job['job_id'] == 'job-1'
        assert job['status'] == 'queued'

    @pytest.mark.asyncio
    async def test_find_job_by_dedupe_key_returns_active_job(self):
        with patch('api.jobs.supabase_service') as mock_svc:
            mock_svc.client.table.return_value = _mock_chain(_mock_result([{
                'job_id': 'job-1',
                'status': 'queued',
                'dedupe_key': 'same-batch',
            }]))

            job = await find_job_by_dedupe_key('same-batch')

        assert job is not None
        assert job['job_id'] == 'job-1'

    @pytest.mark.asyncio
    async def test_record_feishu_push_persists_and_can_be_checked(self):
        with patch('api.jobs.supabase_service') as mock_svc:
            insert_chain = _mock_chain(_mock_result([{'dedupe_key': 'push-doc-1'}]))
            select_chain = _mock_chain(_mock_result([{'dedupe_key': 'push-doc-1'}]))
            mock_svc.client.table.side_effect = [insert_chain, select_chain]

            await record_feishu_push('push-doc-1', 'doc-1', 'template-1')
            exists = await has_feishu_push_record('push-doc-1')

        assert exists is True
        insert_payload = insert_chain.insert.call_args.args[0]
        assert insert_payload['dedupe_key'] == 'push-doc-1'
        assert insert_payload['document_id'] == 'doc-1'
        assert insert_payload['template_id'] == 'template-1'
