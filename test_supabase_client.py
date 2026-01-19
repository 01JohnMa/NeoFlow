"""
临时测试脚本：验证 Supabase 客户端的 HTTP 请求行为
用于诊断 "Not Found" 错误
"""

import os
import sys

# 设置输出编码
sys.stdout.reconfigure(encoding='utf-8')

# 加载 .env 配置
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, ClientOptions
from config.settings import settings

def test_service_role_client():
    """测试 service_role 客户端（应该成功）"""
    print("=" * 60)
    print("测试 1: Service Role 客户端")
    print("=" * 60)
    
    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        result = client.table("documents").select("id, status").limit(1).execute()
        print(f"[OK] 成功! 返回 {len(result.data)} 条记录")
        if result.data:
            print(f"  示例: {result.data[0]}")
        return True
    except Exception as e:
        print(f"[X] 失败: {type(e).__name__}: {e}")
        return False


def test_anon_client():
    """测试 anon 客户端（RLS 会过滤，应该返回空）"""
    print("\n" + "=" * 60)
    print("测试 2: Anon 客户端 (无用户 token)")
    print("=" * 60)
    
    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        result = client.table("documents").select("id, status").limit(1).execute()
        print(f"[OK] 成功! 返回 {len(result.data)} 条记录 (RLS 过滤后)")
        return True
    except Exception as e:
        print(f"[X] 失败: {type(e).__name__}: {e}")
        return False


def test_user_client_current_impl():
    """测试当前的 get_user_client 实现"""
    print("\n" + "=" * 60)
    print("测试 3: 当前 get_user_client 实现 (模拟用户 token)")
    print("=" * 60)
    
    # 使用一个假的但格式正确的 JWT token
    fake_user_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzZmZiOTNlNS1jMTFhLTQyYWMtOWIzYS1iZDFiZTljMzg0MDIiLCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImV4cCI6MTk4MzgxMjk5Nn0.test_signature"
    
    try:
        client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY,
            options=ClientOptions(
                headers={"Authorization": f"Bearer {fake_user_token}"}
            )
        )
        result = client.table("documents").select("id, status").limit(1).execute()
        print(f"[OK] 成功! 返回 {len(result.data)} 条记录")
        return True
    except Exception as e:
        print(f"[X] 失败: {type(e).__name__}: {e}")
        print(f"  错误详情: {str(e)}")
        return False


def test_user_client_fixed_impl():
    """测试修复后的 get_user_client 实现"""
    print("\n" + "=" * 60)
    print("测试 4: 修复后的 get_user_client 实现 (显式设置 apikey)")
    print("=" * 60)
    
    fake_user_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzZmZiOTNlNS1jMTFhLTQyYWMtOWIzYS1iZDFiZTljMzg0MDIiLCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImV4cCI6MTk4MzgxMjk5Nn0.test_signature"
    
    try:
        client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY,
            options=ClientOptions(
                headers={
                    "Authorization": f"Bearer {fake_user_token}",
                    "apikey": settings.SUPABASE_ANON_KEY
                }
            )
        )
        result = client.table("documents").select("id, status").limit(1).execute()
        print(f"[OK] 成功! 返回 {len(result.data)} 条记录")
        return True
    except Exception as e:
        print(f"[X] 失败: {type(e).__name__}: {e}")
        print(f"  错误详情: {str(e)}")
        return False


def test_check_client_rest_url():
    """检查客户端实际使用的 REST URL 和 headers"""
    print("\n" + "=" * 60)
    print("测试 5: 检查客户端 REST URL 和 Headers 配置")
    print("=" * 60)
    
    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        # 尝试获取 postgrest 客户端的 URL 和 headers
        postgrest = client.postgrest
        print(f"  Postgrest session base_url: {postgrest.session.base_url}")
        print(f"  Postgrest session headers: {dict(postgrest.session.headers)}")
        return True
    except Exception as e:
        print(f"[X] 失败: {type(e).__name__}: {e}")
        return False


def test_direct_http_request():
    """直接用 requests 库测试 REST API"""
    print("\n" + "=" * 60)
    print("测试 6: 直接 HTTP 请求 (使用 requests)")
    print("=" * 60)
    
    import requests
    
    url = f"{settings.SUPABASE_URL}/rest/v1/documents?select=id,status&limit=1"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
    }
    
    print(f"  URL: {url}")
    print(f"  Headers: apikey={headers['apikey'][:20]}..., Authorization=Bearer ...")
    
    try:
        response = requests.get(url, headers=headers)
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text[:200]}")
        return response.status_code == 200
    except Exception as e:
        print(f"[X] 失败: {type(e).__name__}: {e}")
        return False


def test_httpx_direct():
    """直接用 httpx 库测试 REST API (supabase-py 使用的库)"""
    print("\n" + "=" * 60)
    print("测试 7: 直接 HTTP 请求 (使用 httpx - 与 supabase-py 相同)")
    print("=" * 60)
    
    import httpx
    
    url = f"{settings.SUPABASE_URL}/rest/v1/documents?select=id,status&limit=1"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
    }
    
    print(f"  URL: {url}")
    
    try:
        with httpx.Client() as client:
            response = client.get(url, headers=headers)
            print(f"  Status: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return response.status_code == 200
    except Exception as e:
        print(f"[X] 失败: {type(e).__name__}: {e}")
        return False


def test_supabase_table_path():
    """检查 supabase-py 实际发送的完整 URL"""
    print("\n" + "=" * 60)
    print("测试 8: 检查 supabase-py 表查询的实际路径")
    print("=" * 60)
    
    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        
        # 获取查询构建器并检查 URL
        query_builder = client.table("documents").select("id, status").limit(1)
        
        # 检查 path 属性
        print(f"  Query path: {query_builder.path}")
        
        # 尝试获取完整 URL
        full_url = f"{client.postgrest.session.base_url}{query_builder.path}"
        print(f"  Expected full URL: {full_url}")
        
        return True
    except Exception as e:
        print(f"[X] 失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_debug_actual_request():
    """调试：检查 supabase-py 实际发送的请求"""
    print("\n" + "=" * 60)
    print("测试 9: 调试 supabase-py 实际请求")
    print("=" * 60)
    
    import httpx
    
    # 启用 httpx 日志
    import logging
    logging.basicConfig(level=logging.DEBUG)
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.DEBUG)
    
    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        result = client.table("documents").select("id").limit(1).execute()
        print(f"[OK] 成功! 返回 {len(result.data)} 条记录")
        return True
    except Exception as e:
        print(f"[X] 失败: {type(e).__name__}: {e}")
        # 打印完整的错误信息
        import traceback
        traceback.print_exc()
        return False
def main():
    print("\n" + "=" * 60)
    print("Supabase 客户端诊断测试")
    print("=" * 60)
    print(f"SUPABASE_URL: {settings.SUPABASE_URL}")
    print(f"ANON_KEY: {settings.SUPABASE_ANON_KEY[:20]}...")
    print(f"SERVICE_ROLE_KEY: {settings.SUPABASE_SERVICE_ROLE_KEY[:20]}...")
    
    results = []
    
    # 先检查 REST URL 配置
    test_check_client_rest_url()
    
    # 直接 HTTP 测试
    results.append(("调试实际请求", test_debug_actual_request()))
    #
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, success in results:
        status = "[OK] 通过" if success else "[X] 失败"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    print("\n" + ("所有测试通过!" if all_passed else "部分测试失败，请检查上述输出"))
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
