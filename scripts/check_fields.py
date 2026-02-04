import asyncio
import httpx
import os

BASE_URL = "https://open.feishu.cn/open-apis"

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_BITABLE_APP_TOKEN = os.getenv("FEISHU_BITABLE_APP_TOKEN")
FEISHU_BITABLE_TABLE_ID = os.getenv("FEISHU_BITABLE_TABLE_ID")

async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 获取 token
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
        
        # 获取字段列表
        resp2 = await client.get(
            f"{BASE_URL}/bitable/v1/apps/{FEISHU_BITABLE_APP_TOKEN}/tables/{FEISHU_BITABLE_TABLE_ID}/fields",
            headers={"Authorization": f"Bearer {token}"}
        )
        result = resp2.json()
        
        if result.get("code") != 0:
            print(f"❌ 获取字段列表失败: {result.get('msg')}")
            return
        
        fields = result.get("data", {}).get("items", [])
        print(f"✅ 找到 {len(fields)} 个字段:\n")
        print("实际字段名列表:")
        for i, field in enumerate(fields, 1):
            field_name = field.get("field_name", "")
            field_type = field.get("type", "")
            print(f"  {i}. {field_name} ({field_type})")
        
        print("\n尝试推送的字段名:")
        push_fields = ['样品名称', '规格型号', '被检单位', '生产商', '检验结论', '文件名称', '附件']
        actual_names = [f.get("field_name") for f in fields]
        
        for i, field_name in enumerate(push_fields, 1):
            exists = field_name in actual_names
            status = "✅" if exists else "❌"
            print(f"  {i}. {field_name} {status}")
        
        # 对比
        missing_fields = set(push_fields) - set(actual_names)
        if missing_fields:
            print(f"\n❌ 缺失的字段: {missing_fields}")
        else:
            print("\n✅ 所有字段都存在")

if __name__ == "__main__":
    asyncio.run(main())
