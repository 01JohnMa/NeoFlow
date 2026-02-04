#!/usr/bin/env python3
"""检查飞书表格字段列表"""

import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_BITABLE_APP_TOKEN = os.getenv("FEISHU_BITABLE_APP_TOKEN")
FEISHU_BITABLE_TABLE_ID = os.getenv("FEISHU_BITABLE_TABLE_ID")

BASE_URL = "https://open.feishu.cn/open-apis"


async def get_tenant_access_token():
    """获取 tenant_access_token"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": FEISHU_APP_ID,
                "app_secret": FEISHU_APP_SECRET
            }
        )
        data = response.json()
        if data.get("code") != 0:
            print(f"获取 token 失败: {data.get('msg')}")
            return None
        return data.get("tenant_access_token")


async def get_table_fields(token, bitable_token, table_id):
    """获取表格字段列表"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/bitable/v1/apps/{bitable_token}/tables/{table_id}/fields",
            headers={
                "Authorization": f"Bearer {token}"
            }
        )
        result = response.json()
        if result.get("code") != 0:
            print(f"获取字段列表失败: code={result.get('code')}, msg={result.get('msg')}")
            return None
        return result.get("data", {}).get("items", [])


async def main():
    print("=== 飞书表格字段检查 ===\n")
    print(f"APP_TOKEN: {FEISHU_BITABLE_APP_TOKEN}")
    print(f"TABLE_ID: {FEISHU_BITABLE_TABLE_ID}\n")
    
    # 获取 token
    print("1. 获取 tenant_access_token...")
    token = await get_tenant_access_token()
    if not token:
        print("❌ 无法获取 token")
        return
    print("✅ Token 获取成功\n")
    
    # 获取字段列表
    print("2. 获取表格字段列表...")
    fields = await get_table_fields(token, FEISHU_BITABLE_APP_TOKEN, FEISHU_BITABLE_TABLE_ID)
    if not fields:
        print("❌ 无法获取字段列表")
        return
    
    print(f"✅ 找到 {len(fields)} 个字段:\n")
    print("实际字段名列表:")
    for i, field in enumerate(fields, 1):
        field_name = field.get("field_name", "")
        field_type = field.get("type", "")
        print(f"  {i}. {field_name} ({field_type})")
    
    print("\n尝试推送的字段名:")
    push_fields = ['样品名称', '规格型号', '被检单位', '生产商', '检验结论', '文件名称', '附件']
    for i, field_name in enumerate(push_fields, 1):
        exists = any(f.get("field_name") == field_name for f in fields)
        status = "✅" if exists else "❌"
        print(f"  {i}. {field_name} {status}")
    
    # 对比
    actual_field_names = [f.get("field_name") for f in fields]
    missing_fields = set(push_fields) - set(actual_field_names)
    if missing_fields:
        print(f"\n❌ 缺失的字段: {missing_fields}")
    else:
        print("\n✅ 所有字段都存在")


if __name__ == "__main__":
    asyncio.run(main())
