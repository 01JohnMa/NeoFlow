# constants/document_types.py
"""文档类型常量定义

统一管理文档类型和数据库表名的映射关系，
避免硬编码字符串散落在多处代码中。
"""


class DocumentTypeTable:
    """文档类型与数据库表名的映射"""
    
    # 数据库表名常量
    INSPECTION_REPORT = "inspection_reports"
    EXPRESS = "expresses"
    SAMPLING_FORM = "sampling_forms"
    LIGHTING_REPORT = "lighting_reports"          # 保留，兼容历史数据
    INTEGRATING_SPHERE = "integrating_sphere_reports"
    LIGHT_DISTRIBUTION = "light_distribution_reports"
    PACKAGING = "packagings"


# 文档类型名称到表名的映射（支持多种别名）
DOC_TYPE_TABLE_MAP = {
    # 检测报告
    "inspection_report": DocumentTypeTable.INSPECTION_REPORT,
    "检测报告": DocumentTypeTable.INSPECTION_REPORT,
    
    # 快递单
    "express": DocumentTypeTable.EXPRESS,
    "快递单": DocumentTypeTable.EXPRESS,
    
    # 抽样单
    "sampling": DocumentTypeTable.SAMPLING_FORM,
    "sampling_form": DocumentTypeTable.SAMPLING_FORM,
    "抽样单": DocumentTypeTable.SAMPLING_FORM,
    
    # 照明综合报告（旧别名，兼容历史数据，不再写入新数据）
    "lighting_combined": DocumentTypeTable.LIGHTING_REPORT,
    "照明综合报告": DocumentTypeTable.LIGHTING_REPORT,
    "照明综合": DocumentTypeTable.LIGHTING_REPORT,
    # 积分球测试（独立表）
    "integrating_sphere": DocumentTypeTable.INTEGRATING_SPHERE,
    "积分球测试": DocumentTypeTable.INTEGRATING_SPHERE,
    # 光分布测试（独立表）
    "light_distribution": DocumentTypeTable.LIGHT_DISTRIBUTION,
    "光分布测试": DocumentTypeTable.LIGHT_DISTRIBUTION,

    # 包装（电连接事业部）
    "packaging": DocumentTypeTable.PACKAGING,
    "包装": DocumentTypeTable.PACKAGING,
}


def get_table_name(doc_type: str) -> str:
    """根据文档类型获取对应的数据库表名
    
    Args:
        doc_type: 文档类型名称或别名
        
    Returns:
        数据库表名，未找到时返回原值
    """
    return DOC_TYPE_TABLE_MAP.get(doc_type, doc_type)
