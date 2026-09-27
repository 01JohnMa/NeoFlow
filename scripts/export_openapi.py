#!/usr/bin/env python3
"""Export the FastAPI OpenAPI document without starting the application lifespan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def export_openapi(output: Path, *, check: bool = False) -> None:
    # Importing the app is sufficient: app.openapi() does not run lifespan hooks,
    # so this export does not initialize Supabase, workers, or an LLM provider.
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from api.main import app

    content = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if check:
        if not output.exists() or output.read_text(encoding="utf-8") != content:
            raise SystemExit("Frozen OpenAPI differs; regenerate and commit before tagging")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=ROOT / "openapi.json",
        help="output path (default: openapi.json)",
    )
    parser.add_argument("--check", action="store_true", help="verify frozen output without writing")
    args = parser.parse_args()
    export_openapi(args.output, check=args.check)


if __name__ == "__main__":
    main()
