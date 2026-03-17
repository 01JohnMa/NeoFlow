# services/feishu_service.py
"""飞书多维表格推送服务 - 支持多租户动态配置"""

import mimetypes
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from config.settings import settings


class FeishuAPIError(Exception):
    """飞书 API 错误"""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"飞书API错误 [{code}]: {message}")


def _is_retryable_feishu_error(exception: Exception) -> bool:
    """判断飞书错误是否可重试
    
    排除以下不可重试的错误：
    - 99991663: 权限不足
    - 1254043: 多维表格不存在
    - 1254060: 字段类型错误
    """
    if isinstance(exception, FeishuAPIError):
        return exception.code not in [99991663, 1254043, 1254060]
    # 网络错误可重试
    return isinstance(exception, (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError))


class FeishuService:
    """飞书 API 服务封装 - 支持多租户
    
    推送目标表格（bitable_token / table_id）统一从 document_templates
    数据库配置读取，由调用方传入；
    """
    
    _instance: Optional['FeishuService'] = None
    _tenant_access_token: Optional[str] = None
    _token_expires_at: Optional[datetime] = None
    
    # 飞书 API 基础 URL
    BASE_URL = "https://open.feishu.cn/open-apis"
    
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

    async def _upload_file_to_feishu(self, file_path: str, parent_node: str) -> Optional[str]:
        """
        上传文件到飞书云文档，返回 file_token

        Args:
            file_path: 本地文件路径
            parent_node: 多维表格 app_token
        """
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"附件文件不存在，跳过上传: {file_path}")
            return None

        token = await self._get_tenant_access_token()
        if not token:
            logger.error("无法获取飞书 token，附件上传失败")
            return None

        try:
            file_size = os.path.getsize(file_path)
            filename = os.path.basename(file_path)
            content_type, _ = mimetypes.guess_type(file_path)
            content_type = content_type or "application/octet-stream"

            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(file_path, "rb") as file_obj:
                    response = await client.post(
                        f"{self.BASE_URL}/drive/v1/medias/upload_all",
                        headers={
                            "Authorization": f"Bearer {token}"
                        },
                        data={
                            "parent_type": "bitable_file",
                            "parent_node": parent_node,
                            "file_type": "file",
                            "file_name": filename,
                            "size": str(file_size)
                        },
                        files={
                            "file": (filename, file_obj, content_type)
                        }
                    )

            result = response.json()
            if result.get("code") != 0:
                logger.error(f"飞书附件上传失败: code={result.get('code')}, msg={result.get('msg')}")
                logger.error(f"完整响应: {result}")
                return None

            file_token = result.get("data", {}).get("file_token")
            if not file_token:
                logger.error("飞书附件上传成功但未返回 file_token")
                return None

            logger.info(f"飞书附件上传成功: {filename}")
            return file_token
        except Exception as e:
            logger.error(f"飞书附件上传异常: {e}")
            return None
    
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
            
            # list/dict 类型直接透传（用于附件等复杂飞书字段）
            if isinstance(value, (list, dict)):
                fields[feishu_field] = value
                continue
            
            # 其他类型统一转为字符串（兼容飞书文本类型列）
            str_value = str(value).strip()
            if str_value:
                fields[feishu_field] = str_value
        
        return fields
    
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
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable_feishu_error),
        reraise=True
    )
    async def _push_to_table_with_retry(
        self,
        bitable_token: str,
        table_id: str,
        fields: Dict[str, Any],
        token: str
    ) -> str:
        """带重试的推送方法（内部使用）
        
        Raises:
            FeishuAPIError: 飞书 API 返回错误
            httpx.TimeoutException: 请求超时
        """
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
                error_msg = result.get("msg", "未知错误")
                
                # 记录详细错误日志
                logger.error(f"飞书多维表格推送失败: code={error_code}, msg={error_msg}")
                logger.error(f"推送的字段: {fields}")
                
                # 常见错误提示
                if error_code == 99991663 or "Forbidden" in str(error_msg):
                    logger.error("权限不足！请在飞书开发者后台添加 bitable:record 权限并发布应用")
                elif error_code == 1254043:
                    logger.error("多维表格不存在或无权访问，请检查 app_token 和 table_id")
                elif error_code == 1254060:
                    logger.error("文本字段转换失败！请检查飞书多维表格的列是否都设置为'文本'类型")
                elif error_code == 1254045:
                    logger.error("字段名不存在(FieldNameNotFound)：推送的列名与飞书多维表格中的列名不一致。请用 scripts/check_feishu_fields.py 拉取该表实际列名，或到飞书开放文档查看「多维表格 - 列出字段」，将模板的 feishu_column 改为与飞书表完全一致。")
                
                raise FeishuAPIError(error_code, error_msg)
            
            return result.get("data", {}).get("record", {}).get("record_id", "")
    
    async def _push_to_table(
        self,
        bitable_token: str,
        table_id: str,
        fields: Dict[str, Any]
    ) -> bool:
        """
        推送数据到指定的飞书多维表格（带重试）
        
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
            record_id = await self._push_to_table_with_retry(
                bitable_token, table_id, fields, token
            )
            logger.info(f"飞书多维表格推送成功, record_id: {record_id}")
            return True
            
        except FeishuAPIError as e:
            # 不可重试的错误已在 _push_to_table_with_retry 中记录
            logger.error(f"飞书推送最终失败: {e}")
            return False
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
