# api/public_schemas.py
"""公共能力端点的对外响应 schema（AI Center 合同消费的 202 形状）。

只描述平台直连端点（POST /parse、POST /extract）的受理响应；
Job 查询与结果端点返回存储行/结果数据，保持原样并以 responses 声明错误码。
"""

from typing import List, Optional

from pydantic import BaseModel


class AcceptedJobData(BaseModel):
    document_id: str
    job_ids: List[str] = []
    job_id: Optional[str] = None
    status: Optional[str] = None
    template_code: Optional[str] = None
    revision_id: Optional[str] = None


class AcceptedJobResponse(BaseModel):
    success: bool
    data: AcceptedJobData


PUBLIC_ERROR_RESPONSES = {
    401: {"description": "缺少或无效的 AI Center 平台上下文"},
    403: {"description": "网关上下文缺少所需 scope"},
    404: {"description": "模板或资源不存在"},
    409: {"description": "活动请求冲突或配置没有已发布修订"},
    422: {"description": "请求参数校验失败"},
    504: {"description": "上游服务超时"},
}
