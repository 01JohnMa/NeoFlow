"""检查照明报告飞书表格字段"""
import asyncio
import httpx
import os

BASE_URL = "https://open.feishu.cn/open-apis"

# 照明报告使用独立的 bitable
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
LIGHTING_BITABLE_TOKEN = "IIJMb0tQNaV5sHsfmX3ccEJLnDb"
LIGHTING_TABLE_ID = "tblDpL7MIZjKX89H"

# 代码中推送的字段名（来自 LIGHTING_REPORT_FIELD_MAPPING + 文件名）
PUSH_FIELDS = [
    "样品型号", "色品坐标X", "色品坐标Y", "Duv", "色温CCT", "Ra", "R9", "CQS", "色容差SDCM",
    "功率(积分球)", "光通量(积分球)", "光效(积分球)", "Rf", "Rg",
    "灯具规格", "功率", "光通量(光分布)", "光效(光分布)", "峰值光强", "光束角",
    "文件名",
]

async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
        )
        data = resp.json()
        token = data.get("tenant_access_token") if data.get("code") == 0 else None
        if not token:
            print("❌ 无法获取 token")
            return
        print("✅ Token 获取成功\n")

        resp2 = await client.get(
            f"{BASE_URL}/bitable/v1/apps/{LIGHTING_BITABLE_TOKEN}/tables/{LIGHTING_TABLE_ID}/fields",
            headers={"Authorization": f"Bearer {token}"}
        )
        result = resp2.json()
        if result.get("code") != 0:
            print(f"❌ 获取字段列表失败: code={result.get('code')}, msg={result.get('msg')}")
            return

        fields = result.get("data", {}).get("items", [])
        print(f"照明表格实际字段（共 {len(fields)} 个）:\n")
        actual_names = []
        for i, field in enumerate(fields, 1):
            name = field.get("field_name", "")
            actual_names.append(name)
            print(f"  {i}. {name} ({field.get('type', '')})")

        print("\n代码推送的字段 vs 表格字段:")
        for name in PUSH_FIELDS:
            exists = name in actual_names
            status = "✅" if exists else "❌"
            print(f"  {name} {status}")

        missing = set(PUSH_FIELDS) - set(actual_names)
        extra_in_table = set(actual_names) - set(PUSH_FIELDS)
        if missing:
            print(f"\n❌ 表格中缺失（代码在推送）: {missing}")
        if extra_in_table:
            print(f"\n表格中多出的列（代码未推送）: {extra_in_table}")
        if not missing:
            print("\n✅ 所有推送字段在表格中都存在")

if __name__ == "__main__":
    asyncio.run(main())
