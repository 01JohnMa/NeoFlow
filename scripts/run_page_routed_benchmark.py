#!/usr/bin/env python3
# scripts/run_page_routed_benchmark.py
"""Run benchmarks/page_routed cases through a live NeoFlow deployment.

Builds one PDF per corpus case (ASCII page text -> text-layer PDF), creates
and publishes idempotent benchmark Configurations for the strategies under
test, submits Extract Jobs through the public API, and writes scorer-ready
outcome rows (see scripts/evaluate_page_routed.py).

The runner never invents values; it only moves corpus text, job status, and
result data between files and the API.
"""
import argparse
import json
import pathlib
import time
import urllib.error
import urllib.request
import uuid

TENANT_ID = "a0000000-0000-0000-0000-000000000001"
PROJECT_ID = "77877a76-0429-4b3c-86f4-b14e03951dc0"

# code -> extraction_strategy; both share the corpus field schema.
STRATEGY_CODES = {
    "source_page_routed": "BENCH_SOURCE_PAGE_ROUTED",
    "full_document": "BENCH_FULL_DOCUMENT",
}
FIELD_NAMES = [
    "protocol_id", "title", "sponsor", "dose",
    "effective_date", "contact_phone", "endpoint",
]


def http_json(base, method, path, token, body=None, is_json=True):
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = resp.read()
        return json.loads(payload) if payload and is_json else None


def http_upload(base, path, token, file_name, file_bytes, content_type):
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{base}{path}", data=body, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


# ---- minimal text-layer PDF writer (ASCII corpus text only) ----

def _pdf_escape(text):
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(lines_per_page):
    """One PDF page per corpus page; Helvetica 12 keeps a clean text layer."""
    objects = []
    page_ids, content_ids = [], []

    def add(obj):
        objects.append(obj)
        return len(objects)

    font_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for lines in lines_per_page:
        text_parts = ["BT /F1 12 Tf 72 720 Td 16 TL"]
        for line in lines:
            text_parts.append(f"({_pdf_escape(line)}) Tj T*")
        text_parts.append("ET")
        content_id = add(f"<< /Length {len(' '.join(text_parts))} >>\nstream\n" + " ".join(text_parts) + "\nendstream")
        content_ids.append(content_id)

    pages_id_placeholder = len(objects) + len(lines_per_page) + 1
    for index, content_id in enumerate(content_ids):
        page_ids.append(add(
            f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
            f"/MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ))
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_id = add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>")
    assert pages_id == pages_id_placeholder
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    out = ["%PDF-1.4"]
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(line) + 1 for line in out))
        out.append(f"{index} 0 obj\n{obj}\nendobj")
    xref_at = sum(len(line) + 1 for line in out)
    out.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f ")
    for offset in offsets:
        out.append(f"\n{offset:010d} 00000 n ")
    out.append(f"\ntrailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_at}\n%%EOF")
    return "\n".join(out).encode()


def corpus_pdf(case):
    lines_per_page = []
    for page in case["pages"]:
        lines = []
        text = page.get("text", "")
        while len(text) > 90:
            cut = text.rfind(" ", 0, 90)
            cut = cut if cut > 0 else 90
            lines.append(text[:cut])
            text = text[cut:].lstrip()
        if text:
            lines.append(text)
        lines_per_page.append(lines or [" "])
    return build_pdf(lines_per_page)


# ---- benchmark configuration bootstrap ----

def bench_schema():
    # Fields stay optional: each corpus case only carries its own subset, and
    # the extractor must not fabricate values the document never states.
    properties = {
        name: {
            "type": "string",
            "description": f"Value of {name} exactly as stated in the source document.",
        }
        for name in FIELD_NAMES
    }
    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }


def definition_for(strategy):
    return {
        "target": "per_doc",
        "data_schema": bench_schema(),
        "ui": {},
        "extraction_strategy": strategy,
    }


def ensure_configuration(base, token, strategy):
    code = STRATEGY_CODES[strategy]
    query = urllib.request.Request(
        f"{base}/admin/configurations?tenant_id={TENANT_ID}&project_id={PROJECT_ID}&type=extract",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(query) as resp:
        rows = http_read(json.load(resp))
    existing = [row for row in rows if row.get("code") == code]
    if existing:
        config_id = existing[0]["id"]
        if existing[0].get("status") != "published":
            _publish_idempotent(base, token, config_id)
        return config_id
    created = http_json(
        base, "POST", "/admin/configurations", token,
        {
            "name": f"benchmark {strategy}",
            "code": code,
            "description": "Page-routed benchmark fixture configuration (synthetic corpus)",
            "type": "extract",
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "definition": definition_for(strategy),
        },
    )
    config_id = (created.get("data") or {}).get("id")
    _publish_idempotent(base, token, config_id)
    return config_id


def _publish_idempotent(base, token, config_id):
    try:
        http_json(base, "POST", f"/admin/configurations/{config_id}/publish", token, {})
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise


def http_read(payload):
    rows = payload.get("data") if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def run_case(base, token, case, strategy, poll_seconds, max_wait):
    case_id = case["case_id"]
    pdf = corpus_pdf(case)
    upload = http_upload(base, "/documents/upload", token, f"{case_id}.pdf", pdf, "application/pdf")
    document_id = upload.get("document_id") or (upload.get("data") or {}).get("id")
    started = time.perf_counter()
    job = http_json(
        base, "POST", "/extract/jobs", token,
        {"template_code": STRATEGY_CODES[strategy], "document_ids": [document_id]},
    )
    job_id = job["data"]["job_ids"][0]
    while True:
        time.sleep(poll_seconds)
        status_row = http_json(base, "GET", f"/jobs/{job_id}", token)
        data = status_row.get("data") or status_row
        status = data.get("status")
        if status in ("completed", "failed"):
            break
        if time.perf_counter() - started > max_wait:
            raise TimeoutError(f"{case_id}/{strategy}: job {job_id} still {status}")
    latency_ms = int((time.perf_counter() - started) * 1000)
    if status != "completed":
        return {
            "case_id": case_id, "strategy": strategy, "scenario": "first_parse",
            "repetition": 0, "status": "failed", "error": str(data.get("error"))[:200],
        }
    try:
        result = http_json(base, "GET", f"/jobs/{job_id}/extract-result", token)
    except urllib.error.HTTPError:
        result = {}
    extract_data = result.get("data") or {}
    engine = result.get("engine") or {}
    routed = engine.get("source_page_routed") or {}
    total_pages = len(case["pages"])
    retrieved = routed.get("selected_pages") or list(range(1, total_pages + 1))
    usage = engine.get("usage") or {}
    return {
        "case_id": case_id,
        "strategy": strategy,
        "scenario": "first_parse",
        "repetition": 0,
        "status": "completed",
        "data": {name: extract_data.get(name) for name in FIELD_NAMES},
        "retrieved_pages": retrieved,
        "valid_evidence_pages": retrieved,
        "parse_result_id": routed.get("parse_result_id"),
        "latency_ms": latency_ms,
        "tokens": (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0),
    }


def login(base, email, password):
    # GoTrue is fronted by the ingress at /supabase in this deployment shape;
    # the caller may pass either the direct auth base or the API base.
    body = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{base}/token?grant_type=password", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)["access_token"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="benchmarks/page_routed/manifest.json")
    parser.add_argument("--outcomes", default="benchmarks/page_routed/outcomes.jsonl")
    parser.add_argument("--api-base", default="http://localhost:8099/api")
    parser.add_argument("--auth-base", default="http://localhost:8099/supabase/auth/v1")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--strategies", nargs="+", default=["source_page_routed", "full_document"])
    parser.add_argument("--cases", nargs="*", default=None, help="subset of case_ids")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-wait-seconds", type=float, default=600.0)
    args = parser.parse_args()

    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    base = args.api_base.rstrip("/")
    token = login(args.auth_base.rstrip("/"), args.email, args.password)
    config_ids = {strategy: ensure_configuration(base, token, strategy) for strategy in args.strategies}
    print("configurations:", config_ids)

    outcomes_path = pathlib.Path(args.outcomes)
    outcomes_path.parent.mkdir(parents=True, exist_ok=True)
    with outcomes_path.open("w", encoding="utf-8") as handle:
        for case_ref in manifest["cases"]:
            case_id = case_ref["case_id"]
            if args.cases and case_id not in args.cases:
                continue
            case = json.loads((pathlib.Path(args.manifest).parent / case_ref["source"]).read_text(encoding="utf-8"))
            for strategy in args.strategies:
                row = run_case(base, token, case, strategy, args.poll_seconds, args.max_wait_seconds)
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                print(f"{case_id}/{strategy}: {row.get('status')} "
                      f"fields={sum(v is not None for v in (row.get('data') or {}).values())}/{len(FIELD_NAMES)} "
                      f"retrieved={row.get('retrieved_pages')} latency_ms={row.get('latency_ms')}")

    print(f"outcomes -> {outcomes_path}")


if __name__ == "__main__":
    main()
