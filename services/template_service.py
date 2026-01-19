# services/template_service.py
"""模板服务 - 文档模板管理和动态 Prompt 构建"""

import json
from typing import Optional, Dict, Any, List
from loguru import logger

from config.settings import settings


class TemplateService:
    """模板服务封装"""
    
    _instance: Optional['TemplateService'] = None
    _client = None
    
    # Prompt 模板骨架
    EXTRACTION_PROMPT_TEMPLATE = """你是一个专业的数据提取助手，专门处理{doc_type}的OCR识别文本。请从用户提供的文本中精准提取以下字段。

**目标字段：**
{field_list}

**处理规则：**
1. 日期格式统一为 YYYY-MM-DD
2. 缺失字段值设为空字符串 ""
3. 数值保持原文精度，保留单位
4. 确保 JSON 语法正确（使用英文双引号、英文逗号）

{examples_section}

**输出要求：**
- 仅输出扁平的 JSON 对象，只包含上述目标字段，禁止添加任何其他字段
- 不要包含任何解释、引言或 Markdown 代码块标记

现在，请处理用户提供的OCR文本：
{ocr_text}"""
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _get_client(self):
        """获取 Supabase 客户端"""
        if self._client is None:
            from services.supabase_service import supabase_service
            self._client = supabase_service.client
        return self._client
    
    # ============ 模板操作 ============
    
    async def get_tenant_templates(
        self, 
        tenant_id: str, 
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取租户的所有模板
        
        Args:
            tenant_id: 租户ID
            active_only: 是否只返回启用的模板
            
        Returns:
            模板列表
        """
        try:
            query = self._get_client().table("document_templates").select(
                "id, tenant_id, name, code, description, process_mode, required_doc_count, sort_order"
            ).eq("tenant_id", tenant_id)
            
            if active_only:
                query = query.eq("is_active", True)
            
            query = query.order("sort_order").order("name")
            result = query.execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"获取租户模板列表失败: {e}")
            return []
    
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        获取模板详情
        
        Args:
            template_id: 模板ID
            
        Returns:
            模板信息
        """
        try:
            result = self._get_client().table("document_templates").select("*").eq("id", template_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取模板失败: {e}")
            return None
    
    async def get_template_by_code(
        self, 
        tenant_id: str, 
        code: str
    ) -> Optional[Dict[str, Any]]:
        """
        根据代码获取模板（含字段和示例）
        
        Args:
            tenant_id: 租户ID
            code: 模板代码
            
        Returns:
            模板信息（含 fields 和 examples）
        """
        try:
            # 获取模板基本信息
            result = self._get_client().table("document_templates").select(
                "*, template_fields(*), template_examples(*)"
            ).eq("tenant_id", tenant_id).eq("code", code).execute()
            
            if not result.data:
                return None
            
            template = result.data[0]
            
            # 排序字段
            if template.get("template_fields"):
                template["template_fields"].sort(key=lambda x: x.get("sort_order", 0))
            
            # 排序示例
            if template.get("template_examples"):
                template["template_examples"].sort(key=lambda x: x.get("sort_order", 0))
                # 只保留启用的示例
                template["template_examples"] = [
                    ex for ex in template["template_examples"] 
                    if ex.get("is_active", True)
                ]
            
            return template
        except Exception as e:
            logger.error(f"获取模板失败: {e}")
            return None
    
    async def get_template_with_details(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        获取模板完整信息（含字段、示例、合并规则）
        
        Args:
            template_id: 模板ID
            
        Returns:
            模板完整信息
        """
        try:
            result = self._get_client().table("document_templates").select(
                "*, template_fields(*), template_examples(*), template_merge_rules(*)"
            ).eq("id", template_id).execute()
            
            if not result.data:
                return None
            
            template = result.data[0]
            
            # 排序字段和示例
            if template.get("template_fields"):
                template["template_fields"].sort(key=lambda x: x.get("sort_order", 0))
            
            if template.get("template_examples"):
                template["template_examples"].sort(key=lambda x: x.get("sort_order", 0))
                template["template_examples"] = [
                    ex for ex in template["template_examples"] 
                    if ex.get("is_active", True)
                ]
            
            return template
        except Exception as e:
            logger.error(f"获取模板详情失败: {e}")
            return None
    
    # ============ 字段操作 ============
    
    async def get_template_fields(self, template_id: str) -> List[Dict[str, Any]]:
        """
        获取模板的字段列表
        
        Args:
            template_id: 模板ID
            
        Returns:
            字段列表
        """
        try:
            result = self._get_client().table("template_fields").select(
                "*"
            ).eq("template_id", template_id).order("sort_order").execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"获取模板字段失败: {e}")
            return []
    
    # ============ 示例操作 ============
    
    async def get_template_examples(
        self, 
        template_id: str, 
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取模板的 few-shot 示例列表
        
        Args:
            template_id: 模板ID
            active_only: 是否只返回启用的示例
            
        Returns:
            示例列表
        """
        try:
            query = self._get_client().table("template_examples").select(
                "*"
            ).eq("template_id", template_id)
            
            if active_only:
                query = query.eq("is_active", True)
            
            query = query.order("sort_order")
            result = query.execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"获取模板示例失败: {e}")
            return []
    
    # ============ 合并规则操作 ============
    
    async def get_merge_rule(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        获取模板的合并规则
        
        Args:
            template_id: 模板ID
            
        Returns:
            合并规则
        """
        try:
            result = self._get_client().table("template_merge_rules").select(
                "*, sub_template_a:sub_template_a_id(*), sub_template_b:sub_template_b_id(*)"
            ).eq("template_id", template_id).execute()
            
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取合并规则失败: {e}")
            return None
    
    # ============ 动态 Prompt 构建 ============
    
    def build_extraction_prompt(
        self, 
        template: Dict[str, Any], 
        ocr_text: str
    ) -> str:
        """
        根据模板配置动态构建 LLM 提取 Prompt
        
        Args:
            template: 模板信息（含 template_fields 和 template_examples）
            ocr_text: OCR 识别文本
            
        Returns:
            构建好的 Prompt
        """
        # 1. 构建字段列表
        fields = template.get("template_fields", [])
        field_lines = []
        for i, field in enumerate(fields, 1):
            field_key = field.get("field_key", "")
            field_label = field.get("field_label", "")
            field_type = field.get("field_type", "text")
            
            type_hint = ""
            if field_type == "date":
                type_hint = "（日期格式：YYYY-MM-DD）"
            elif field_type == "number":
                type_hint = "（数值类型）"
            
            field_lines.append(f"| {i} | {field_label} | {field_key} | {type_hint}")
        
        field_list = "| 序号 | 字段含义 | JSON键名 | 说明 |\n|------|----------|----------|------|\n" + "\n".join(field_lines)
        
        # 2. 构建示例部分
        examples = template.get("template_examples", [])
        examples_section = ""
        
        if examples:
            examples_section = "**参考示例：**\n"
            for i, ex in enumerate(examples, 1):
                example_input = ex.get("example_input", "").strip()
                example_output = ex.get("example_output", {})
                
                # 格式化输出
                if isinstance(example_output, str):
                    try:
                        example_output = json.loads(example_output)
                    except:
                        pass
                
                output_str = json.dumps(example_output, ensure_ascii=False)
                
                examples_section += f"\n示例{i}输入文本片段：\n{example_input}\n\n示例{i}输出：\n{output_str}\n"
        
        # 3. 组装完整 Prompt
        prompt = self.EXTRACTION_PROMPT_TEMPLATE.format(
            doc_type=template.get("name", "文档"),
            field_list=field_list,
            examples_section=examples_section,
            ocr_text=ocr_text
        )
        
        return prompt
    
    def build_field_mapping(self, template: Dict[str, Any]) -> Dict[str, str]:
        """
        构建字段到飞书列名的映射
        
        Args:
            template: 模板信息（含 template_fields）
            
        Returns:
            {field_key: feishu_column} 映射
        """
        fields = template.get("template_fields", [])
        mapping = {}
        
        for field in fields:
            field_key = field.get("field_key")
            feishu_column = field.get("feishu_column")
            
            if field_key and feishu_column:
                mapping[field_key] = feishu_column
        
        return mapping
    
    def get_field_keys(self, template: Dict[str, Any]) -> List[str]:
        """
        获取模板的所有字段键名列表
        
        Args:
            template: 模板信息
            
        Returns:
            字段键名列表
        """
        fields = template.get("template_fields", [])
        return [f.get("field_key") for f in fields if f.get("field_key")]
    
    # ============ Merge 模式支持 ============
    
    async def get_merge_template_info(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 merge 模式模板的完整信息（包含子模板）
        
        Args:
            template_id: 合并模板ID
            
        Returns:
            合并模板信息，包含子模板 A 和 B 的完整配置
        """
        try:
            # 获取主模板
            template = await self.get_template_with_details(template_id)
            if not template:
                return None
            
            if template.get("process_mode") != "merge":
                return template
            
            # 获取合并规则
            merge_rules = template.get("template_merge_rules", [])
            if not merge_rules:
                return template
            
            merge_rule = merge_rules[0]
            
            # 获取子模板详情
            sub_template_a_id = merge_rule.get("sub_template_a_id")
            sub_template_b_id = merge_rule.get("sub_template_b_id")
            
            if sub_template_a_id:
                template["sub_template_a"] = await self.get_template_with_details(sub_template_a_id)
            
            if sub_template_b_id:
                template["sub_template_b"] = await self.get_template_with_details(sub_template_b_id)
            
            return template
        except Exception as e:
            logger.error(f"获取合并模板信息失败: {e}")
            return None
    
    def merge_extraction_results(
        self, 
        result_a: Optional[Dict[str, Any]], 
        result_b: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        合并两份文档的提取结果
        
        Args:
            result_a: 文档A的提取结果
            result_b: 文档B的提取结果
            
        Returns:
            合并后的结果
        """
        merged = {}
        
        if result_a:
            merged.update(result_a)
        
        if result_b:
            merged.update(result_b)
        
        return merged


# 单例实例
template_service = TemplateService()
