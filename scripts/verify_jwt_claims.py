#!/usr/bin/env python3
"""验证 JWT claims 是否正确传递到 PostgREST

测试步骤：
1. 使用用户 JWT 调用 PostgREST 的 RPC 函数
2. 验证 auth.uid() 是否返回正确的用户ID
3. 验证 get_current_user_tenant_id() 是否返回正确的租户ID

使用方法：
    python scripts/verify_jwt_claims.py --token <user_jwt_token>
    
或在 Python 中：
    from scripts.verify_jwt_claims import verify_jwt_claims
    result = verify_jwt_claims(user_jwt_token)
"""

import requests
import jwt
import argparse
import json
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings


def verify_jwt_claims(user_token: str) -> dict:
    """
    验证 JWT claims 是否正确传递到 PostgREST
    
    Args:
        user_token: 用户的 JWT access token
        
    Returns:
        验证结果字典
    """
    result = {
        "success": False,
        "jwt_decoded": None,
        "auth_uid": None,
        "auth_role": None,
        "auth_jwt": None,
        "tenant_id": None,
        "user_role": None,
        "errors": []
    }
    
    # 1. 解码 JWT（不验证签名）
    try:
        decoded = jwt.decode(user_token, options={"verify_signature": False})
        result["jwt_decoded"] = {
            "sub": decoded.get("sub"),
            "role": decoded.get("role"),
            "aud": decoded.get("aud"),
            "exp": decoded.get("exp")
        }
        print(f"✓ JWT 解码成功: sub={decoded.get('sub')}, role={decoded.get('role')}")
    except Exception as e:
        result["errors"].append(f"JWT 解码失败: {e}")
        print(f"✗ JWT 解码失败: {e}")
        return result
    
    # 设置请求头
    headers = {
        "Authorization": f"Bearer {user_token}",
        "apikey": settings.SUPABASE_ANON_KEY,
        "Content-Type": "application/json"
    }
    
    base_url = settings.SUPABASE_URL
    
    # 2. 测试 auth.uid() - 创建一个 RPC 函数调用
    # 由于 PostgREST 不能直接调用 auth.uid()，我们通过查询一个使用它的 RPC
    print(f"\n调用 PostgREST: {base_url}/rest/v1/")
    
    # 2a. 测试 get_current_user_tenant_id()
    try:
        url = f"{base_url}/rest/v1/rpc/get_current_user_tenant_id"
        response = requests.post(url, headers=headers)
        
        if response.status_code == 200:
            tenant_id = response.json()
            result["tenant_id"] = tenant_id
            if tenant_id:
                print(f"✓ get_current_user_tenant_id() = {tenant_id}")
            else:
                print(f"⚠ get_current_user_tenant_id() = NULL (可能是 auth.uid() 返回 NULL)")
                result["errors"].append("tenant_id 为 NULL，auth.uid() 可能未正确设置")
        else:
            print(f"✗ RPC 调用失败: {response.status_code} - {response.text}")
            result["errors"].append(f"RPC 调用失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 请求失败: {e}")
        result["errors"].append(str(e))
    
    # 2b. 测试 get_current_user_role()
    try:
        url = f"{base_url}/rest/v1/rpc/get_current_user_role"
        response = requests.post(url, headers=headers)
        
        if response.status_code == 200:
            user_role = response.json()
            result["user_role"] = user_role
            if user_role:
                print(f"✓ get_current_user_role() = {user_role}")
            else:
                print(f"⚠ get_current_user_role() = NULL")
        else:
            print(f"✗ RPC 调用失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 请求失败: {e}")
    
    # 3. 尝试查询 documents 表验证 RLS
    try:
        url = f"{base_url}/rest/v1/documents?select=id,user_id,status&limit=5"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            docs = response.json()
            print(f"\n✓ documents 查询成功，返回 {len(docs)} 条记录")
            if docs:
                for doc in docs[:3]:
                    print(f"  - {doc.get('id')[:8]}... user_id={doc.get('user_id')[:8] if doc.get('user_id') else 'N/A'}...")
                result["success"] = len(docs) > 0
            else:
                print(f"  (无记录，可能是 RLS 过滤导致或用户确实没有文档)")
                # 如果 tenant_id 也是 NULL，则确认是 JWT claims 问题
                if result["tenant_id"] is None:
                    result["errors"].append("RLS 可能因 auth.uid()=NULL 而过滤了所有记录")
        else:
            print(f"✗ documents 查询失败: {response.status_code} - {response.text}")
            result["errors"].append(f"documents 查询失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 请求失败: {e}")
        result["errors"].append(str(e))
    
    # 4. 使用 service_role 验证数据确实存在
    print(f"\n--- 使用 service_role 对比验证 ---")
    service_headers = {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        user_id = decoded.get("sub")
        url = f"{base_url}/rest/v1/documents?select=id,user_id,status&user_id=eq.{user_id}&limit=5"
        response = requests.get(url, headers=service_headers)
        
        if response.status_code == 200:
            docs = response.json()
            print(f"✓ service_role 查询该用户文档: {len(docs)} 条")
            
            if docs and not result["success"]:
                print(f"\n⚠ 问题确认: service_role 能查到 {len(docs)} 条文档，但用户 JWT 查不到")
                print(f"  → 说明 RLS 策略 user_id = auth.uid() 失败")
                print(f"  → auth.uid() 返回的不是 {user_id}")
                result["errors"].append(f"RLS 问题确认：数据存在但被 RLS 过滤")
        else:
            print(f"✗ service_role 查询失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 请求失败: {e}")
    
    # 总结
    print(f"\n{'='*50}")
    if result["tenant_id"] and result["success"]:
        print("✓ 验证通过！JWT claims 已正确传递到 PostgREST")
        result["success"] = True
    elif result["tenant_id"]:
        print("⚠ 部分通过：tenant_id 可以获取，但 documents 查询异常")
    else:
        print("✗ 验证失败！JWT claims 未正确传递")
        print("\n可能的原因：")
        print("  1. Kong hide_credentials 仍为 true")
        print("  2. PostgREST PGRST_DB_USE_LEGACY_GUCS 未正确设置")
        print("  3. 用户 profile 中 tenant_id 为空")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="验证 JWT claims 传递")
    parser.add_argument("--token", "-t", help="用户 JWT token", required=True)
    args = parser.parse_args()
    
    print("="*50)
    print("JWT Claims 验证工具")
    print("="*50)
    
    result = verify_jwt_claims(args.token)
    
    print(f"\n结果 JSON:")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
