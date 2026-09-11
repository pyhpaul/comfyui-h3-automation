#!/usr/bin/env python3
"""Upload job media to Comfy and write Load-able bound workflows (no queue).

Writes API format always; also UI format (original YZ layout) when
templates/<name>/workflow_ui.json exists unless --api-only.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from comfy_orch.client import ComfyClient
from comfy_orch.export_bound import export_bound_workflow_for_job
from comfy_orch.paths import project_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_dir", type=Path)
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        help="API JSON output (default: <job>/bound_workflow_api.json)",
    )
    parser.add_argument(
        "--out-ui",
        type=Path,
        help="UI JSON output (default: <job>/bound_workflow_ui.json)",
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Do not write UI-format workflow",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("COMFY_BASE_URL", ""),
        help="Comfy base URL (or COMFY_BASE_URL)",
    )
    args = parser.parse_args()
    if not args.base_url:
        raise SystemExit("set COMFY_BASE_URL or pass --base-url")

    job_dir = args.job_dir.resolve()
    out = (args.out or (job_dir / "bound_workflow_api.json")).resolve()
    out_ui = None if args.api_only else (args.out_ui or (job_dir / "bound_workflow_ui.json")).resolve()
    root = project_root()
    client = ComfyClient(args.base_url)
    try:
        client.system_stats()
        api_path, ui_path = export_bound_workflow_for_job(
            job_dir,
            root=root,
            client=client,
            out_path=out,
            out_ui_path=out_ui,
        )
    finally:
        client.close()
    print(api_path)
    if ui_path:
        print(ui_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
