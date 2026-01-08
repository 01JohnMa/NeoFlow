# services/feishu_service.py
"""飞书多维表格推送服务"""

import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

from config.settings import settings


class FeishuService:
    """飞书 API 服务封装"""
    
    _instance: Optional['FeishuService'] = None
    _tenant_access_token: Optional[str] = None
    _token_expires_at: Optional[datetime] = None
    
    # 飞书 API 基础 URL
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    # inspection_reports 字段到飞书多维表格列名的映射
    FIELD_MAPPING = {
        "sample_name": "样品名称",
        "specification_model": "规格型号",
        "production_date_batch": "生产日期批次",
        "inspected_unit_name": "被检单位",
        "inspected_unit_address": "被检单位地址",
        "manufacturer_name": "生产商",
        "manufacturer_address": "生产商地址",
        "task_source": "任务来源",
        "sampling_agency": "抽样机构",
        "sampling_date": "抽样日期",
        "inspection_conclusion": "检验结论",
        "inspection_category": "检验类别",
        "inspector": "检验员",
        "reviewer": "审核人",
        "approver": "批准人",
        "notes": "备注",
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _is_configured(self) -> bool:
        """检查飞书配置是否完整"""
        return bool(
            settings.FEISHU_APP_ID and
            settings.FEISHU_APP_SECRET and
            settings.FEISHU_BITABLE_APP_TOKEN and
            settings.FEISHU_BITABLE_TABLE_ID
        )
    
    async def _get_tenant_access_token(self) -> Optional[str]:
        """
        获取 tenant_access_token（应用身份凭证）
        
        Token 有效期为 2 小时，会自动缓存和刷新
        """
        # 检查缓存的 token 是否有效
        if (self._tenant_access_token and 
            self._token_expires_at and 
            datetime.now() < self._token_expires_at):
            return self._tenant_access_token
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": settings.FEISHU_APP_ID,
                        "app_secret": settings.FEISHU_APP_SECRET
                    }
                )
                
                data = response.json()
                
                if data.get("code") != 0:
                    logger.error(f"获取飞书 token 失败: {data.get('msg')}")
                    return None
                
                self._tenant_access_token = data.get("tenant_access_token")
                # Token 有效期 2 小时，提前 5 分钟刷新
                expire_seconds = data.get("expire", 7200) - 300
                self._token_expires_at = datetime.now() + timedelta(seconds=expire_seconds)
                
                logger.info("飞书 tenant_access_token 获取成功")
                return self._tenant_access_token
                
        except Exception as e:
            logger.error(f"获取飞书 token 异常: {e}")
            return None
    
    def _convert_to_feishu_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 inspection_reports 数据转换为飞书多维表格字段格式
        
        Args:
            data: inspection_reports 表的数据
            
        Returns:
            飞书多维表格字段格式的数据
        """
        fields = {}
        
        for db_field, feishu_field in self.FIELD_MAPPING.items():
            value = data.get(db_field)
            
            if value is None or value == "":
                continue
            
            # 处理日期字段 - 跳过无效日期
            if db_field == "sampling_date" and value:
                try:
                    if isinstance(value, str):
                        # 只处理标准格式的日期
                        dt = datetime.strptime(value, "%Y-%m-%d")
                        fields[feishu_field] = int(dt.timestamp() * 1000)
                except Exception:
                    # 日期格式无效，跳过该字段
                    logger.debug(f"跳过无效日期字段: {value}")
                    continue
            # 处理文本字段 - 确保是字符串
            else:
                str_value = str(value).strip()
                if str_value:  # 跳过空字符串
                    fields[feishu_field] = str_value
        
        return fields
    
    async def push_inspection_report(self, data: Dict[str, Any]) -> bool:
        """
        推送检验报告数据到飞书多维表格
        
        Args:
            data: inspection_reports 表的记录数据
            
        Returns:
            推送是否成功
        """
        # 检查是否启用推送
        if not settings.FEISHU_PUSH_ENABLED:
            logger.debug("飞书推送未启用，跳过")
            return True
        
        # 检查配置是否完整
        if not self._is_configured():
            logger.warning("飞书配置不完整，跳过推送")
            return False
        
        # 获取 token
        token = await self._get_tenant_access_token()
        if not token:
            logger.error("无法获取飞书 token，推送失败")
            return False
        
        # 转换字段格式
        fields = self._convert_to_feishu_fields(data)
        
        if not fields:
            logger.warning("没有有效字段可推送")
            return False
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/bitable/v1/apps/{settings.FEISHU_BITABLE_APP_TOKEN}/tables/{settings.FEISHU_BITABLE_TABLE_ID}/records",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    json={"fields": fields}
                )
                
                result = response.json()
                
                if result.get("code") != 0:
                    error_code = result.get("code")
                    error_msg = result.get("msg")
                    logger.error(f"飞书多维表格推送失败: code={error_code}, msg={error_msg}")
                    # 常见错误提示
                    if error_code == 99991663 or "Forbidden" in str(error_msg):
                        logger.error("权限不足！请在飞书开发者后台添加 bitable:record 权限并发布应用")
                    elif error_code == 1254043:
                        logger.error("多维表格不存在或无权访问，请检查 app_token 和 table_id")
                    return False
                
                record_id = result.get("data", {}).get("record", {}).get("record_id")
                logger.info(f"飞书多维表格推送成功, record_id: {record_id}")
                return True
                
        except Exception as e:
            logger.error(f"飞书多维表格推送异常: {e}")
            return False
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        测试飞书连接
        
        Returns:
            包含测试结果的字典
        """
        result = {
            "configured": self._is_configured(),
            "enabled": settings.FEISHU_PUSH_ENABLED,
            "token_valid": False,
            "message": ""
        }
        
        if not result["configured"]:
            result["message"] = "飞书配置不完整"
            return result
        
        token = await self._get_tenant_access_token()
        result["token_valid"] = bool(token)
        
        if token:
            result["message"] = "飞书连接测试成功"
        else:
            result["message"] = "获取飞书 token 失败"
        
        return result


# 单例实例
feishu_service = FeishuService()
