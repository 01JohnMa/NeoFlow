#!/usr/bin/env python3
"""检查飞书表格字段列表，对比「实际列名」与「当前推送的列名」是否一致。

用法:
  python scripts/check_feishu_fields.py
  python scripts/check_feishu_fields.py <APP_TOKEN> <TABLE_ID>

若未传 APP_TOKEN/TABLE_ID，则使用 .env 中的 FEISHU_BITABLE_APP_TOKEN / FEISHU_BITABLE_TABLE_ID。
检测报告模板使用的表可在 document_templates 表中查 feishu_bitable_token、feishu_table_id。
"""

import asyncio
import httpx
import os
import sys
from dotenv import load_dotenv

load_dotenv()

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_BITABLE_APP_TOKEN = os.getenv("FEISHU_BITABLE_APP_TOKEN")
FEISHU_BITABLE_TABLE_ID = os.getenv("FEISHU_BITABLE_TABLE_ID")

BASE_URL = "https://open.feishu.cn/open-apis"

# 检测报告模板当前推送的列名（与 002_init_data 中 feishu_column 及 文件名/附件 一致）
PUSH_FIELDS_INSPECTION = [
    "样品名称", "规格型号", "生产日期/批号",
    "受检单位-名称", "受检单位-地址", "受检单位-电话",
    "生产单位-名称", "生产单位-地址", "生产单位-电话",
    "任务来源", "抽样机构", "抽样日期",
    "检验结论", "检验类别", "备注", "主检", "审核", "批准",
    "文件名", "附件",
]


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
    app_token = FEISHU_BITABLE_APP_TOKEN
    table_id = FEISHU_BITABLE_TABLE_ID
    if len(sys.argv) >= 3:
        app_token, table_id = sys.argv[1], sys.argv[2]
    if not app_token or not table_id:
        print("请设置 .env 中的 FEISHU_BITABLE_APP_TOKEN、FEISHU_BITABLE_TABLE_ID，或传入: APP_TOKEN TABLE_ID")
        return

    print("=== 飞书表格字段检查 ===\n")
    print(f"APP_TOKEN: {app_token}")
    print(f"TABLE_ID: {table_id}\n")

    print("1. 获取 tenant_access_token...")
    token = await get_tenant_access_token()
    if not token:
        print("❌ 无法获取 token")
        return
    print("✅ Token 获取成功\n")

    print("2. 获取表格字段列表...")
    fields = await get_table_fields(token, app_token, table_id)
    if not fields:
        print("❌ 无法获取字段列表")
        return

    actual_names = [f.get("field_name", "") for f in fields]
    print(f"✅ 飞书表中共 {len(actual_names)} 个列\n")
    print("飞书表实际列名:")
    for i, name in enumerate(actual_names, 1):
        print(f"  {i}. {name}")

    print("\n当前检测报告推送的列名 与 飞书表 对比:")
    for name in PUSH_FIELDS_INSPECTION:
        exists = name in actual_names
        status = "✅" if exists else "❌ 不存在"
        print(f"  {name} -> {status}")

    missing = set(PUSH_FIELDS_INSPECTION) - set(actual_names)
    if missing:
        print(f"\n❌ 飞书表中缺失的列（会导致 FieldNameNotFound）: {missing}")
        print("   处理方式：在飞书多维表格中新增同名列，或修改模板 feishu_column 为飞书表已有列名。")
    else:
        print("\n✅ 所有推送列在飞书表中均存在。")


if __name__ == "__main__":
    asyncio.run(main())
