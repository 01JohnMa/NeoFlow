#!/usr/bin/env python3
"""
一次性脚本：将 profiles 表中的所有用户设为管理员权限

用法:
  # 将全体用户设为租户管理员 (tenant_admin)
  python scripts/set_all_users_admin.py --role tenant_admin

  # 将全体用户设为超级管理员 (super_admin)
  python scripts/set_all_users_admin.py --role super_admin

  # 仅将 role='user' 的普通用户提升为租户管理员（不改动已有的 tenant_admin/super_admin）
  python scripts/set_all_users_admin.py --role tenant_admin --only-user
"""

import asyncio
import argparse
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.supabase_service import supabase_service
from loguru import logger


def set_all_users_admin(role: str, only_user: bool = False) -> int:
    """
    批量更新用户角色

    Args:
        role: 目标角色 tenant_admin 或 super_admin
        only_user: 若为 True，仅更新 role='user' 的用户；否则更新全部

    Returns:
        更新的记录数
    """
    client = supabase_service.client
    if not client:
        logger.error("Supabase 客户端未初始化，请检查 .env 中的 SUPABASE_SERVICE_ROLE_KEY")
        return 0

    if role not in ("tenant_admin", "super_admin"):
        logger.error("role 必须是 tenant_admin 或 super_admin")
        return 0

    try:
        query = client.table("profiles").update({"role": role}).select("id")
        if only_user:
            query = query.eq("role", "user")
        result = query.execute()
        count = len(result.data) if result.data else 0
        logger.info(f"已将 {count} 个用户设为 {role}")
        return count
    except Exception as e:
        logger.error(f"更新失败: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description="将全体用户设为管理员权限")
    parser.add_argument(
        "--role",
        choices=["tenant_admin", "super_admin"],
        default="tenant_admin",
        help="目标角色：tenant_admin（租户管理员）或 super_admin（超级管理员）",
    )
    parser.add_argument(
        "--only-user",
        action="store_true",
        help="仅更新 role='user' 的普通用户，不改动已有的 tenant_admin/super_admin",
    )
    args = parser.parse_args()
    count = set_all_users_admin(role=args.role, only_user=args.only_user)
    print(f"已更新 {count} 条记录")


if __name__ == "__main__":
    main()
