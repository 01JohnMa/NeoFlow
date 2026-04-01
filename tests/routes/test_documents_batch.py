import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import DOCUMENT_ID, TEMPLATE_ID
from api.routes.documents.batch import BatchItem, _process_merge_item, _process_single_item


def _mock_supabase_result(data=None):
    result = MagicMock()
    result.data = data if data is not None else []
    return result


def _mock_supabase_chain(data=None):
    chain = MagicMock()
    for method in ('select', 'eq', 'limit', 'order', 'insert', 'update', 'or_'):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = _mock_supabase_result(data)
    return chain


class TestBatchProcessRoute:
    def test_batch_process_returns_existing_job_when_same_payload_already_queued(self, client):
        payload = {
            'items': [
                {
                    'document_id': DOCUMENT_ID,
                    'template_id': TEMPLATE_ID,
                }
            ]
        }

        with patch('api.routes.documents.batch.template_service') as mock_ts, \
             patch('api.routes.documents.batch.supabase_service') as mock_svc, \
             patch('api.routes.documents.batch.find_job_by_dedupe_key', return_value={'job_id': 'job-existing', 'status': 'queued'}), \
             patch('api.routes.documents.batch.create_job') as mock_create_job, \
             patch('api.routes.documents.batch.asyncio.create_task') as mock_create_task:
            mock_ts.get_template = AsyncMock(return_value={'id': TEMPLATE_ID, 'tenant_id': 'tenant-001'})
            mock_svc.get_document = AsyncMock(return_value={'id': DOCUMENT_ID, 'file_path': '/tmp/doc.pdf'})

            resp = client.post('/api/documents/batch-process', json=payload)

        assert resp.status_code == 202
        data = resp.json()
        assert data['job_id'] == 'job-existing'
        assert data['status'] == 'queued'
        mock_create_job.assert_not_called()
        mock_create_task.assert_not_called()


class TestBatchProcessCustomPushName:
    @pytest.mark.asyncio
    async def test_single_item_uses_request_custom_push_name_over_document_value(self, mock_user):
        item = BatchItem(
            document_id='doc-a',
            template_id='tpl-a',
            custom_push_name='本次最新文件名',
        )

        with patch('api.routes.documents.batch.supabase_service') as mock_svc, \
             patch('api.routes.documents.batch.template_service') as mock_ts, \
             patch('api.routes.documents.batch.ocr_workflow') as mock_wf, \
             patch('api.routes.documents.batch.handle_processing_success', new_callable=AsyncMock) as mock_handle_success, \
             patch('api.routes.documents.batch.update_batch_item'), \
             patch('os.path.exists', return_value=True):
            mock_svc.get_document = AsyncMock(return_value={
                'id': 'doc-a',
                'file_path': '/tmp/doc-a.pdf',
                'custom_push_name': '旧文件名',
            })
            mock_ts.get_template = AsyncMock(return_value={'id': 'tpl-a', 'auto_approve': False})
            mock_wf.process_with_template = AsyncMock(return_value={
                'success': True,
                'extraction_data': {'sample_no': 'A-001'},
            })

            await _process_single_item('job-1', 0, item, mock_user)

        assert mock_handle_success.await_args.kwargs['custom_push_name'] == '本次最新文件名'

    @pytest.mark.asyncio
    async def test_merge_item_uses_request_custom_push_name_over_document_value(self, mock_user):
        item = BatchItem(
            document_id='doc-a',
            template_id='tpl-a',
            paired_document_id='doc-b',
            paired_template_id='tpl-b',
            custom_push_name='本次最新组合名',
        )

        with patch('api.routes.documents.batch.supabase_service') as mock_svc, \
             patch('api.routes.documents.batch.template_service') as mock_ts, \
             patch('api.routes.documents.batch.ocr_workflow') as mock_wf, \
             patch('api.routes.documents.batch.push_to_feishu', new_callable=AsyncMock) as mock_push, \
             patch('api.routes.documents.batch.update_batch_item'), \
             patch('os.path.exists', return_value=True):
            mock_svc.get_document = AsyncMock(side_effect=[
                {'id': 'doc-a', 'file_path': '/tmp/doc-a.pdf', 'custom_push_name': '旧组合名'},
                {'id': 'doc-b', 'file_path': '/tmp/doc-b.pdf', 'custom_push_name': '旧组合名'},
            ])
            mock_ts.get_template_with_details = AsyncMock(side_effect=[
                {'id': 'tpl-a', 'name': '模板A', 'auto_approve': True, 'push_attachment': True},
                {'id': 'tpl-b', 'name': '模板B', 'auto_approve': True, 'push_attachment': True},
            ])
            mock_wf.process_merge = AsyncMock(return_value={
                'success': True,
                'extraction_results': [
                    {'sample_index': 1, 'data': {'sample_no': 'A-001'}},
                ],
                'sub_results': {
                    'results_a': [{'sample_no': 'A-001'}],
                    'results_b': [{'report_no': 'B-001'}],
                },
            })

            await _process_merge_item('job-1', 0, item, mock_user)

        assert mock_push.await_args.kwargs['custom_push_name'] == '本次最新组合名'
