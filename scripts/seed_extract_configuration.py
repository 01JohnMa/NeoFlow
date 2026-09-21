#!/usr/bin/env python3
"""Create the checked-in Extract seed as a draft through the normal admin API.

Requires explicit tenant/project and NEOFLOW_API_TOKEN. Never publishes or
updates an existing configuration. No database migration or stored-data conversion.
"""

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Dict
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.extract_configuration import validate_extract_definition  # noqa: E402

SEED = ROOT / "configurations/seeds/prj-basic-info-drug-registration.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("管理 API 发生重定向；为避免泄露令牌，请直接指定最终 API 地址")


def seed_configuration(
    request: Callable[[str, str, Any], Any], payload: Dict[str, Any],
    tenant_id: str, project_id: str,
) -> Dict[str, Any]:
    if not tenant_id.strip() or not project_id.strip():
        raise ValueError("必须显式指定 tenant_id 和 project_id")
    definition = validate_extract_definition(payload["definition"])
    params = urlencode({"tenant_id": tenant_id, "project_id": project_id, "type": "extract"})
    rows = request("GET", f"/admin/configurations?{params}", None)
    if not isinstance(rows, list):
        raise ValueError("配置列表返回格式异常")
    # Do not rely on the server honoring filters for an administrator token.
    matches = [row for row in rows if row.get("tenant_id") == tenant_id
               and row.get("project_id") == project_id and row.get("code") == payload["code"]]
    if len(matches) > 1:
        raise ValueError("发现多个相同 code 的配置；拒绝自动选择或覆盖")
    if matches:
        existing = matches[0]
        expected = {key: payload.get(key) for key in ("name", "code", "description", "type")}
        if existing.get("draft_definition") != definition or any(existing.get(key) != value for key, value in expected.items()):
            raise ValueError("相同 code 已存在但内容不同；保留用户配置，不覆盖")
        return {"action": "unchanged", "configuration_id": existing["id"], "status": existing["status"]}
    body = {**payload, "definition": definition, "tenant_id": tenant_id, "project_id": project_id}
    response = request("POST", "/admin/configurations", body)
    created = response.get("data") if isinstance(response, dict) else None
    if not isinstance(created, dict) or created.get("status") != "draft":
        raise ValueError("创建响应异常；请按 code 检查是否已创建，不要盲目重试")
    if created.get("tenant_id") != tenant_id or created.get("project_id") != project_id:
        raise ValueError("创建响应的租户或项目不匹配")
    return {"action": "created", "configuration_id": created["id"], "status": "draft"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="API base including any path prefix")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    token = os.environ.get("NEOFLOW_API_TOKEN")
    if not token:
        parser.error("请在环境变量 NEOFLOW_API_TOKEN 中提供管理员令牌；不要写入仓库")
    parsed = urlparse(args.base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("base-url 必须是合法 HTTP(S) URL，不能包含账号或密码")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("远程 API 必须使用 HTTPS，避免明文发送令牌")

    def request(method: str, path: str, body: Any) -> Any:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = Request(args.base_url.rstrip("/") + path, data=data, method=method,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with build_opener(NoRedirect).open(req, timeout=30) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            # Do not echo response bodies that might include credentials or documents.
            raise RuntimeError(f"管理 API 返回 HTTP {exc.code}；未自动重试或覆盖配置") from exc

    try:
        payload = json.loads(SEED.read_text(encoding="utf-8"))
        result = seed_configuration(request, payload, args.tenant_id, args.project_id)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
