import pytest
from unittest.mock import AsyncMock, patch

from api.routes.documents.batch import BatchItem, _process_merge_item, _process_single_item


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
                    'result_b': {'report_no': 'B-001'},
                },
            })

            await _process_merge_item('job-1', 0, item, mock_user)

        assert mock_push.await_args.kwargs['custom_push_name'] == '本次最新组合名'
