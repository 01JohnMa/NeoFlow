#!/usr/bin/env python3
"""
测试用户 JWT 在 PostgREST 中的 claims 解析

运行方式：
    python test_user_jwt.py <user_jwt_token>
"""

import requests
import jwt
import sys

SUPABASE_URL = 'http://localhost:8000'
ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0'
SERVICE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU'

def test_user_jwt(user_token: str):
    # 解码 JWT 获取 user_id
    try:
        decoded = jwt.decode(user_token, options={"verify_signature": False})
        user_id = decoded.get('sub')
        role = decoded.get('role')
        print(f'JWT 解码:')
        print(f'  sub (user_id): {user_id}')
        print(f'  role: {role}')
    except Exception as e:
        print(f'JWT 解码失败: {e}')
        return

    # 使用用户 JWT 访问 PostgREST
    headers_user = {
        'Authorization': f'Bearer {user_token}',
        'apikey': ANON_KEY,
        'Content-Type': 'application/json'
    }

    # 测试 1: 调用 get_current_user_tenant_id()
    print(f'\n测试 1: 用户 JWT 调用 get_current_user_tenant_id()...')
    resp = requests.post(f'{SUPABASE_URL}/rest/v1/rpc/get_current_user_tenant_id', headers=headers_user)
    print(f'  状态码: {resp.status_code}')
    if resp.status_code == 200:
        tenant_id = resp.json()
        print(f'  返回 tenant_id: {tenant_id}')
        if tenant_id is None:
            print(f'  ⚠ tenant_id 为 NULL！说明 auth.uid() 可能返回 NULL')
    else:
        print(f'  错误: {resp.text}')

    # 测试 2: 用户 JWT 查询 documents
    print(f'\n测试 2: 用户 JWT 查询 documents...')
    resp = requests.get(f'{SUPABASE_URL}/rest/v1/documents?select=id,user_id,status&limit=5', headers=headers_user)
    print(f'  状态码: {resp.status_code}')
    if resp.status_code == 200:
        docs = resp.json()
        print(f'  返回文档数: {len(docs)}')
        if len(docs) == 0:
            print(f'  ⚠ 没有返回任何文档！RLS 可能因 auth.uid()=NULL 而过滤了所有记录')
        else:
            for doc in docs[:3]:
                print(f'    - {doc.get("id")[:8]}... status={doc.get("status")}')
    else:
        print(f'  错误: {resp.text}')

    # 测试 3: 查询特定文档
    doc_id = '204d456e-7f90-4ed4-aa1b-b47177da4007'
    print(f'\n测试 3: 用户 JWT 查询文档 {doc_id}...')
    resp = requests.get(f'{SUPABASE_URL}/rest/v1/documents?id=eq.{doc_id}&select=*', headers=headers_user)
    print(f'  状态码: {resp.status_code}')
    if resp.status_code == 200:
        docs = resp.json()
        if docs:
            print(f'  ✓ 找到文档!')
        else:
            print(f'  ✗ 文档被 RLS 过滤，无法访问')
    else:
        print(f'  错误: {resp.text}')

    # 测试 4: 直接用 SQL 检查 auth.uid() 的值
    # 创建一个临时 RPC 函数来返回 auth.uid()
    print(f'\n测试 4: 创建临时函数检查 auth.uid()...')
    # 先用 service_role 创建一个测试函数
    headers_service = {
        'Authorization': f'Bearer {SERVICE_KEY}',
        'apikey': SERVICE_KEY,
        'Content-Type': 'application/json'
    }
    
    # 检查是否已存在
    print(f'  调用 debug_auth_uid() 函数...')
    resp = requests.post(f'{SUPABASE_URL}/rest/v1/rpc/debug_auth_uid', headers=headers_user)
    if resp.status_code == 200:
        result = resp.json()
        print(f'  auth.uid() 返回: {result}')
        if result is None:
            print(f'  ⚠ auth.uid() 返回 NULL！PostgREST 没有正确解析 JWT claims')
    elif resp.status_code == 404:
        print(f'  函数不存在，需要先创建')
    else:
        print(f'  错误: {resp.status_code} - {resp.text}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python test_user_jwt.py <user_jwt_token>')
        print('\n获取用户 JWT:')
        print('  1. 在浏览器中打开开发者工具 (F12)')
        print('  2. 进入 Application/Storage > Local Storage')
        print('  3. 找到 supabase.auth.token 或类似键')
        print('  4. 复制 access_token 的值')
        sys.exit(1)
    
    test_user_jwt(sys.argv[1])
