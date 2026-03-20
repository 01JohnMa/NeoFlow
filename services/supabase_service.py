# services/supabase_service.py
"""Supabase 数据库服务 - 本地部署版"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, List

from loguru import logger
from supabase import create_client, Client

from config.settings import settings
from constants.document_types import DocumentTypeTable, DOC_TYPE_TABLE_MAP


class SupabaseService:
    """Supabase 服务封装"""
    
    _instance: Optional['SupabaseService'] = None
    _client: Optional[Client] = None
    
    # ============ 表格映射（使用常量模块） ============
    # 支持模板 code、中文名和历史别名，降低耦合性
    TABLE_MAP = DOC_TYPE_TABLE_MAP
    
    # 各表的日期字段定义（使用常量模块的表名）
    DATE_FIELDS = {
        DocumentTypeTable.SAMPLING_FORM: ["sampling_date", "production_date", "expiry_date"],
        DocumentTypeTable.INSPECTION_REPORT: ["report_date", "inspection_date", "sample_date"],
        DocumentTypeTable.EXPRESS: ["shipping_date", "delivery_date"],
    }
    
    # 非日期字段（字段名包含 date 但不应进行日期格式校验的复合字段）
    NON_DATE_FIELDS = ["production_date_batch"]
    
    # ALLOWED_FIELDS 白名单已移除。
    # 入库前字段过滤现在通过 schema_sync_service.get_columns() 动态读取
    # 结果表的实际物理列来实现，详见 _filter_allowed_fields()。
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _clean_data_for_db(self, data: Dict[str, Any], table_name: str) -> Dict[str, Any]:
        """清理数据，将无效日期字段转换为 None"""
        cleaned = data.copy()
        date_fields = self.DATE_FIELDS.get(table_name, [])
        
        for key, value in cleaned.items():
            # 判断是否为日期字段（排除复合字段如 production_date_batch）
            is_date_field = (key in date_fields or "date" in key.lower()) and key not in self.NON_DATE_FIELDS
            
            if is_date_field and isinstance(value, str):
                # 空字符串转为 None
                if value == "" or value.strip() == "":
                    cleaned[key] = None
                else:
                    # 验证日期格式是否有效 (YYYY-MM-DD)
                    validated_date = self._validate_and_fix_date(value)
                    cleaned[key] = validated_date
        
        return cleaned

    def _normalize_lighting_units(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """修正常见 OCR 单位错误（如 lm 被识别为 1m）"""
        if not data:
            return data

        def fix_lm_unit(value: Any) -> Any:
            if not isinstance(value, str):
                return value
            normalized = value
            # 处理常见错误：1m/W -> lm/W
            normalized = re.sub(r'(?i)\b1m\s*/\s*w\b', 'lm/W', normalized)
            # 处理单位错误：数字后 1m -> lm（例如 1200 1m）
            normalized = re.sub(r'(?i)(?<=\d)\s*1m\b', 'lm', normalized)
            # 兜底：独立 1m -> lm
            normalized = re.sub(r'(?i)\b1m\b', 'lm', normalized)
            return normalized

        normalized = data.copy()
        target_fields = [
            "luminous_flux",
            "luminous_efficacy",
            "luminous_flux_sphere",
            "luminous_efficacy_sphere",
        ]
        for field in target_fields:
            if field in normalized:
                normalized[field] = fix_lm_unit(normalized[field])

        return normalized
    
    def _filter_allowed_fields(self, data: Dict[str, Any], table_name: str) -> Dict[str, Any]:
        """
        过滤数据，只保留结果表中实际存在的物理列。

        使用 schema_sync_service 动态读取列名（带本地缓存），
        避免硬编码白名单与数据库实际结构脱节。

        降级策略：若无法获取列名（如网络异常），允许所有字段通过，
        让数据库层自行报错（已记录 warning 日志）。
        """
        from services.schema_sync_service import schema_sync_service

        actual_columns = schema_sync_service.get_columns(table_name)

        if not actual_columns:
            # 列查询失败时降级：放行所有字段，由数据库层报错
            logger.warning(f"无法获取表 {table_name} 的列名，跳过字段过滤（降级模式）")
            return data

        filtered = {k: v for k, v in data.items() if k in actual_columns}

        removed = set(data.keys()) - set(filtered.keys())
        if removed:
            logger.warning(f"过滤掉不在表 {table_name} 中的字段: {removed}")

        return filtered
    
    def _validate_and_fix_date(self, date_str: str) -> Optional[str]:
        """
        验证并修复日期格式，返回有效的 YYYY-MM-DD 格式或 None
        
        支持的输入格式：
        - YYYY-MM-DD (标准格式，直接返回)
        - YYYY/MM/DD, YYYY.MM.DD (转换为标准格式)
        - YYYYMMDD (8位数字格式)
        - 无效格式返回 None
        """
        if not date_str or not isinstance(date_str, str):
            return None
        
        date_str = date_str.strip()
        
        # 清理 OCR 识别中常见的尾部/头部噪声字符
        # 例如 '2025-03-29//' -> '2025-03-29'
        date_str = re.sub(r'^[/\-.\s]+|[/\-.\s]+$', '', date_str)
        
        # 尝试多种日期格式解析
        date_formats = [
            "%Y-%m-%d",   # 2025-01-07
            "%Y/%m/%d",   # 2025/01/07
            "%Y.%m.%d",   # 2025.01.07
            "%Y年%m月%d日",  # 2025年01月07日
            "%Y%m%d",     # 20250107 (8位数字)
        ]
        
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                return parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        # 如果所有格式都失败，检查是否只有年份或年月
        # 这种情况下返回 None，因为数据库要求完整日期
        logger.warning(f"无效的日期格式 '{date_str}'，将设为 None")
        return None
    
    async def initialize(self):
        """初始化Supabase客户端"""
        try:
            self._client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY
            )
            logger.info(f"✓ Supabase连接成功: {settings.SUPABASE_URL}")
            return True
        except Exception as e:
            logger.error(f"✗ Supabase连接失败: {e}")
            raise
    
    @property
    def client(self) -> Client:
        if not self._client:
            raise RuntimeError("Supabase未初始化，请先调用initialize()")
        return self._client
    
    def get_user_client(self, user_token: str) -> Client:
        """
        根据用户 JWT token 创建 Supabase client（应用 RLS 策略）
        
        Args:
            user_token: 用户的 JWT access token
            
        Returns:
            配置了用户身份的 Supabase Client，自动应用 RLS 策略
        """
        from supabase import ClientOptions
        
        return create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY,
            options=ClientOptions(
                headers={
                    "Authorization": f"Bearer {user_token}"
                }
            )
        )
    
    def get_table_name(self, document_type: str) -> Optional[str]:
        """根据文档类型获取表名（支持中文和英文）"""
        return self.TABLE_MAP.get(document_type)

    def resolve_table_name(
        self,
        template_id: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        统一解析业务表名。

        查找顺序：
        1. 若提供 template_id，查询 document_templates.target_table（优先）
        2. fallback 到 TABLE_MAP 静态映射（兼容旧数据）
        """
        if template_id:
            row = self.client.table("document_templates").select("target_table").eq("id", template_id).execute()
            target = (row.data[0].get("target_table") or "") if row.data else ""
            if target:
                return target
        return self.TABLE_MAP.get(document_type) if document_type else None

    # ============ 文档操作 ============
    
    async def create_document(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建文档记录"""
        try:
            result = self.client.table("documents").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.bind(data_keys=sorted(data.keys())).opt(exception=e).error("创建文档失败")
            raise
    
    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取文档"""
        try:
            result = self.client.table("documents").select("*").eq("id", document_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取文档失败: {e}")
            raise
    
    async def update_document(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新文档"""
        try:
            result = self.client.table("documents").update(data).eq("id", document_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"更新文档失败: {e}")
            raise
    
    async def delete_document(self, document_id: str) -> bool:
        """删除文档"""
        try:
            self.client.table("documents").delete().eq("id", document_id).execute()
            return True
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return False
    
    async def update_document_status(
        self, 
        document_id: str, 
        status: str, 
        error_message: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """更新文档状态"""
        data = {"status": status}
        if error_message:
            data["error_message"] = error_message
        if status == "completed":
            data["processed_at"] = datetime.now().isoformat()
        
        return await self.update_document(document_id, data)
    
    async def list_documents(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        document_type: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """列出文档"""
        try:
            query = self.client.table("documents").select("*")
            
            if user_id:
                query = query.eq("user_id", user_id)
            if status:
                query = query.eq("status", status)
            if document_type:
                query = query.eq("document_type", document_type)
            
            offset = (page - 1) * limit
            query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
            
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"列出文档失败: {e}")
            return []
    
    async def count_documents(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        document_type: Optional[str] = None
    ) -> int:
        """统计文档数量"""
        try:
            query = self.client.table("documents").select("id", count="exact")
            
            if user_id:
                query = query.eq("user_id", user_id)
            if status:
                query = query.eq("status", status)
            if document_type:
                query = query.eq("document_type", document_type)
            
            result = query.execute()
            return result.count or 0
        except Exception as e:
            logger.error(f"统计文档失败: {e}")
            return 0
    
    # ============ 通用数据操作方法 ============
    
    async def _save_to_table(
        self, 
        table_name: str, 
        document_id: str, 
        data: Dict[str, Any],
        normalize_func: Optional[callable] = None
    ) -> Optional[Dict[str, Any]]:
        """通用保存方法 - 保存数据到指定表
        
        Args:
            table_name: 数据库表名
            document_id: 文档ID
            data: 要保存的数据
            normalize_func: 可选的数据规范化函数（如照明报告的单位修正）
            
        Returns:
            保存后的记录，失败时抛出异常
        """
        try:
            # 1. 过滤掉 AI 返回的额外字段
            filtered_data = self._filter_allowed_fields(data, table_name)
            # 2. 保存原始提取数据（含额外字段，用于调试）
            filtered_data["raw_extraction_data"] = data.copy()
            # 3. 可选的数据规范化处理
            if normalize_func:
                filtered_data = normalize_func(filtered_data)
            # 4. 设置文档ID
            filtered_data["document_id"] = document_id
            # 5. 清理数据，处理空日期字段
            cleaned_data = self._clean_data_for_db(filtered_data, table_name)
            # 6. 执行 upsert
            result = self.client.table(table_name).upsert(
                cleaned_data, on_conflict="document_id"
            ).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"保存到 {table_name} 失败: {e}")
            raise
    
    async def _get_from_table(
        self, 
        table_name: str, 
        document_id: str
    ) -> Optional[Dict[str, Any]]:
        """通用获取方法 - 根据文档ID获取记录
        
        Args:
            table_name: 数据库表名
            document_id: 文档ID
            
        Returns:
            记录数据，不存在或失败时返回 None
        """
        try:
            result = self.client.table(table_name).select("*").eq(
                "document_id", document_id
            ).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"从 {table_name} 获取数据失败: {e}")
            return None
    
    # ============ 检验报告操作 ============
    
    async def save_inspection_report(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """保存检验报告"""
        return await self._save_to_table("inspection_reports", document_id, data)
    
    async def get_inspection_report(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取检验报告"""
        return await self._get_from_table("inspection_reports", document_id)
    
    # ============ 快递单操作 ============
    
    async def save_express(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """保存快递单"""
        return await self._save_to_table("expresses", document_id, data)
    
    async def get_express(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取快递单"""
        return await self._get_from_table("expresses", document_id)
    
    # ============ 抽样单操作 ============
    
    async def save_sampling_form(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """保存抽样单"""
        return await self._save_to_table("sampling_forms", document_id, data)
    
    async def get_sampling_form(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取抽样单"""
        return await self._get_from_table("sampling_forms", document_id)
    
    # ============ 包装操作 ============

    async def save_packaging(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """保存包装信息"""
        return await self._save_to_table("packagings", document_id, data)

    async def get_packaging(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取包装信息"""
        return await self._get_from_table("packagings", document_id)

    # ============ 照明报告操作 ============
    
    async def save_lighting_report(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """保存照明综合报告（含单位规范化）"""
        return await self._save_to_table(
            "lighting_reports", 
            document_id, 
            data, 
            normalize_func=self._normalize_lighting_units
        )
    
    async def get_lighting_report(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取照明综合报告"""
        return await self._get_from_table("lighting_reports", document_id)
    
    # ============ 文档查询辅助方法 ============
    
    async def get_document_by_file_path(self, file_path: str) -> Optional[Dict[str, Any]]:
        """根据文件路径获取文档"""
        try:
            result = self.client.table("documents").select("*").eq("file_path", file_path).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"根据路径获取文档失败: {e}")
            return None
    
    # ============ 通用保存方法 ============
    
    async def save_extraction_result(
        self,
        document_id: str,
        document_type: str,
        extraction_data: Dict[str, Any],
        template_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """根据文档类型保存提取结果（优先 template_id → target_table，fallback TABLE_MAP）。"""
        table_name = self.resolve_table_name(template_id=template_id, document_type=document_type)
        if not table_name:
            logger.error(
                f"未知文档类型: {document_type}，无法保存提取结果。"
                f"document_id={document_id}, fields={list(extraction_data.keys())}"
            )
            return None
        return await self._save_to_table(table_name, document_id, extraction_data)
    
    async def get_extraction_result(
        self, 
        document_id: str, 
        document_type: str
    ) -> Optional[Dict[str, Any]]:
        """根据文档类型获取提取结果"""
        table_name = self.get_table_name(document_type)
        if not table_name:
            return None
        
        try:
            result = self.client.table(table_name).select("*").eq("document_id", document_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取提取结果失败: {e}")
            return None
    
    async def update_extraction_result(
        self,
        document_id: str,
        document_type: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """根据文档类型更新提取结果"""
        try:
            table_name = self.get_table_name(document_type)
            if not table_name:
                logger.warning(f"未知文档类型: {document_type}")
                return None
            
            # 更新记录
            result = self.client.table(table_name).update(data).eq("document_id", document_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"更新提取结果失败: {e}")
            raise
    
    # ============ 处理日志 ============
    
    async def log_processing(
        self,
        document_id: str,
        step: str,
        status: str,
        message: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """记录处理日志"""
        try:
            data = {
                "document_id": document_id,
                "step": step,
                "status": status,
                "message": message,
                "duration_ms": duration_ms
            }
            result = self.client.table("processing_logs").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"记录处理日志失败: {e}")
            return None
    
    async def get_processing_logs(self, document_id: str) -> List[Dict[str, Any]]:
        """获取处理日志"""
        try:
            result = self.client.table("processing_logs").select("*").eq("document_id", document_id).order("created_at").execute()
            return result.data or []
        except Exception as e:
            logger.error(f"获取处理日志失败: {e}")
            return []


    # ============ 文件命名工具 ============
    
    def generate_display_name(
        self, 
        document_type: str, 
        extraction_data: Dict[str, Any],
        original_file_name: Optional[str] = None
    ) -> str:
        """
        根据文档类型和提取结果生成规范的显示名称
        
        命名规则：
        - 检验报告(测试单): 报告_{样品名称}_{规格型号}_{抽样日期}
        - 快递单: 快递_{快递单号}_{收件人}
        - 抽样单: 抽样_{产品名称}_{省份城市}
        - 未知类型: 文档_{当前时间}
        
        Args:
            document_type: 文档类型
            extraction_data: 提取的数据
            original_file_name: 原始文件名(备用)
            
        Returns:
            规范化的显示名称
        """
        _INSPECTION_TYPES = {"inspection_report", "检测报告"}
        _EXPRESS_TYPES = {"快递单", "express"}
        _SAMPLING_TYPES = {"抽样单", "sampling_form", "sampling"}

        def clean_name(name: Optional[str], max_len: int = 20) -> str:
            if not name:
                return ""
            prefixes = ["微信图片_", "IMG_", "Screenshot_", "image_"]
            for prefix in prefixes:
                if name.startswith(prefix):
                    name = name[len(prefix):]
            name = name.rsplit('.', 1)[0] if '.' in name else name
            name = ''.join(c for c in name if c.isalnum() or c in '-_')
            return name[:max_len] if len(name) > max_len else name

        try:
            if document_type in _INSPECTION_TYPES:
                sample_name = clean_name(extraction_data.get("sample_name"))
                specification_model = clean_name(extraction_data.get("specification_model"))
                sampling_date = extraction_data.get("sampling_date", "")
                if sample_name:
                    name_parts = ["报告", sample_name]
                    if specification_model:
                        name_parts.append(specification_model)
                    if sampling_date:
                        name_parts.append(sampling_date)
                    return "_".join(name_parts)

            elif document_type in _EXPRESS_TYPES:
                tracking = clean_name(extraction_data.get("tracking_number"), max_len=15)
                recipient = clean_name(extraction_data.get("recipient"), max_len=10)
                if tracking:
                    return f"快递_{tracking}_{recipient}" if recipient else f"快递_{tracking}"
                elif recipient:
                    return f"快递_{recipient}"

            elif document_type in _SAMPLING_TYPES:
                # 抽样单: 抽样_{产品名称}_{省份城市}
                product = clean_name(extraction_data.get("product_name"))
                province = extraction_data.get("sampled_province", "")
                city = extraction_data.get("sampled_city", "")
                location = f"{province}{city}".strip()
                if product:
                    if location:
                        return f"抽样_{product}_{location}"
                    return f"抽样_{product}"
            
            elif document_type in ["照明综合报告", "lighting_combined", "integrating_sphere", "积分球测试"]:
                # 照明报告: 照明_{样品型号}_{色温}
                sample_model = clean_name(extraction_data.get("sample_model"))
                cct = clean_name(extraction_data.get("cct"), max_len=10)
                if sample_model:
                    if cct:
                        return f"照明_{sample_model}_{cct}"
                    return f"照明_{sample_model}"
            
            # 如果无法生成有意义的名称，使用时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            type_prefix = {
                "inspection_report": "报告",
                "检测报告": "报告",
                "快递单": "快递",
                "express": "快递",
                "抽样单": "抽样",
                "sampling_form": "抽样",
                "sampling": "抽样",
                "照明综合报告": "照明",
                "lighting_combined": "照明",
                "integrating_sphere": "照明",
                "积分球测试": "照明",
            }.get(document_type, "文档")
            
            return f"{type_prefix}_{timestamp}"
            
        except Exception as e:
            logger.warning(f"生成显示名称失败: {e}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"文档_{timestamp}"
    
    async def update_display_name(self, document_id: str, display_name: str) -> Optional[Dict[str, Any]]:
        """更新文档的显示名称"""
        return await self.update_document(document_id, {"display_name": display_name})


# 单例实例
supabase_service = SupabaseService()



