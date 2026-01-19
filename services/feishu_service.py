# services/feishu_service.py
"""飞书多维表格推送服务 - 支持多租户动态配置"""

import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from loguru import logger

from config.settings import settings


class FeishuService:
    """飞书 API 服务封装 - 支持多租户"""
    
    _instance: Optional['FeishuService'] = None
    _tenant_access_token: Optional[str] = None
    _token_expires_at: Optional[datetime] = None
    
    # 飞书 API 基础 URL
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    # 【向后兼容】inspection_reports 字段到飞书多维表格列名的默认映射
    # 新模板请使用数据库配置的 template_fields.feishu_column
    DEFAULT_FIELD_MAPPING = {
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
    
    # 向后兼容别名
    FIELD_MAPPING = DEFAULT_FIELD_MAPPING
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _is_configured(self) -> bool:
        """检查飞书基础配置是否完整（应用凭证）"""
        return bool(
            settings.FEISHU_APP_ID and
            settings.FEISHU_APP_SECRET
        )
    
    def _is_default_table_configured(self) -> bool:
        """检查默认表格配置是否完整（向后兼容）"""
        return bool(
            self._is_configured() and
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
        【向后兼容】将 inspection_reports 数据转换为飞书多维表格字段格式
        
        Args:
            data: inspection_reports 表的数据
            
        Returns:
            飞书多维表格字段格式的数据
        """
        return self._convert_by_field_mapping(data, self.DEFAULT_FIELD_MAPPING)
    
    def _convert_by_field_mapping(
        self, 
        data: Dict[str, Any], 
        field_mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        根据字段映射将数据转换为飞书多维表格字段格式
        
        Args:
            data: 提取的数据
            field_mapping: {数据字段: 飞书列名} 映射
            
        Returns:
            飞书多维表格字段格式的数据
        """
        fields = {}
        
        for db_field, feishu_field in field_mapping.items():
            value = data.get(db_field)
            
            if value is None or value == "":
                continue
            
            # 所有字段统一转为字符串（兼容飞书文本类型列）
            str_value = str(value).strip()
            if str_value:  # 跳过空字符串
                fields[feishu_field] = str_value
        
        return fields
    
    async def push_inspection_report(self, data: Dict[str, Any]) -> bool:
        """
        【向后兼容】推送检验报告数据到飞书多维表格（使用默认配置）
        
        Args:
            data: inspection_reports 表的记录数据
            
        Returns:
            推送是否成功
        """
        # 检查是否启用推送
        if not settings.FEISHU_PUSH_ENABLED:
            logger.debug("飞书推送未启用，跳过")
            return True
        
        # 检查默认表格配置是否完整
        if not self._is_default_table_configured():
            logger.warning("飞书默认表格配置不完整，跳过推送")
            return False
        
        # 转换字段格式
        fields = self._convert_to_feishu_fields(data)
        
        # 使用默认表格配置推送
        return await self._push_to_table(
            settings.FEISHU_BITABLE_APP_TOKEN,
            settings.FEISHU_BITABLE_TABLE_ID,
            fields
        )
    
    async def push_by_template(
        self, 
        data: Dict[str, Any],
        field_mapping: Dict[str, str],
        bitable_token: str,
        table_id: str
    ) -> bool:
        """
        根据模板配置推送数据到飞书多维表格（多租户支持）
        
        Args:
            data: 提取的数据
            field_mapping: 字段映射 {数据字段: 飞书列名}
            bitable_token: 多维表格 app_token
            table_id: 数据表 table_id
            
        Returns:
            推送是否成功
        """
        # 检查是否启用推送
        if not settings.FEISHU_PUSH_ENABLED:
            logger.debug("飞书推送未启用，跳过")
            return True
        
        # 检查基础配置
        if not self._is_configured():
            logger.warning("飞书应用配置不完整，跳过推送")
            return False
        
        # 检查表格配置
        if not bitable_token or not table_id:
            logger.warning("模板的飞书表格配置不完整，跳过推送")
            return False
        
        # 转换字段格式
        fields = self._convert_by_field_mapping(data, field_mapping)
        
        # 推送到指定表格
        return await self._push_to_table(bitable_token, table_id, fields)
    
    async def _push_to_table(
        self,
        bitable_token: str,
        table_id: str,
        fields: Dict[str, Any]
    ) -> bool:
        """
        推送数据到指定的飞书多维表格
        
        Args:
            bitable_token: 多维表格 app_token
            table_id: 数据表 table_id
            fields: 已转换的飞书字段数据
            
        Returns:
            推送是否成功
        """
        if not fields:
            logger.warning("没有有效字段可推送")
            return False
        
        # 获取 token
        token = await self._get_tenant_access_token()
        if not token:
            logger.error("无法获取飞书 token，推送失败")
            return False
        
        # 调试：打印要推送的字段
        logger.info(f"准备推送到飞书的字段: {list(fields.keys())}")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/bitable/v1/apps/{bitable_token}/tables/{table_id}/records",
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
                    logger.error(f"完整响应: {result}")
                    logger.error(f"推送的字段: {fields}")
                    # 常见错误提示
                    if error_code == 99991663 or "Forbidden" in str(error_msg):
                        logger.error("权限不足！请在飞书开发者后台添加 bitable:record 权限并发布应用")
                    elif error_code == 1254043:
                        logger.error("多维表格不存在或无权访问，请检查 app_token 和 table_id")
                    elif error_code == 1254060:
                        logger.error("文本字段转换失败！请检查飞书多维表格的列是否都设置为'文本'类型")
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
