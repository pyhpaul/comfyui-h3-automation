"""Read SSH host/port/password from the open Chenyu podExample tab via CDP.

Uses the user's already-open tab at https://www.chenyu.cn/console/podExample.
Password is written to passfiles (mode 600) and never printed by default.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable


PROXY = "http://localhost:3456"
PAGE_ID = re.compile(r"实例ID[:：]\s*([0-9a-f]{16,})")
HOST_RE = re.compile(r"连接主机：\s*\n?\s*([^\s\n]+)")
PORT_RE = re.compile(r"端口：\s*\n?\s*(\d+)")
USER_RE = re.compile(r"用户：\s*\n?\s*([^\s\n]+)")
PASS_RE = re.compile(r"密码：\s*\n?\s*([^\s\n]+)")
CMD_RE = re.compile(r"连接命令：\s*\n?\s*(ssh[^\n]+)")


def parse_ssh_block(text: str) -> dict[str, str] | None:
    if "SSH 登录信息" not in text and "连接主机" not in text:
        return None
    host = HOST_RE.search(text)
    port = PORT_RE.search(text)
    user = USER_RE.search(text)
    password = PASS_RE.search(text)
    cmd = CMD_RE.search(text)
    if not (host and port and user and password):
        return None
    return {
        "host": host.group(1).strip(),
        "port": port.group(1).strip(),
        "user": user.group(1).strip(),
        "password": password.group(1).strip(),
        "cmd": (cmd.group(1).strip() if cmd else ""),
    }


def list_running_ids(page_text: str) -> list[str]:
    ids = PAGE_ID.findall(page_text)
    out: list[str] = []
    for page_id in ids:
        if page_id in out:
            continue
        idx = page_text.find(page_id)
        slice_ = page_text[idx : idx + 900] if idx >= 0 else ""
        if "运行中" in slice_:
            out.append(page_id)
    return out


def _target_id(proxy: str) -> str:
    with urllib.request.urlopen(proxy + "/targets", timeout=8) as response:
        raw = json.load(response)
    items = raw if isinstance(raw, list) else raw.get("targets") or raw.get("data") or []
    for tab in items:
        if isinstance(tab, dict) and "chenyu.cn/console/podExample" in (tab.get("url") or ""):
            target = tab.get("id") or tab.get("targetId") or ""
            if target:
                return target
    raise RuntimeError("podExample tab is not open")


def _post(proxy: str, path: str, body: str, timeout: float = 15) -> object:
    request = urllib.request.Request(
        proxy + path,
        data=body.encode(),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _eval(proxy: str, target: str, expression: str) -> object:
    raw = _post(proxy, "/eval?target=" + target, expression)
    if isinstance(raw, dict) and "value" in raw:
        return raw["value"]
    return raw


def _click_at(proxy: str, target: str, selector: str) -> object:
    return _post(proxy, "/clickAt?target=" + target, selector)


MARK_SSH = r"""
(() => {
  const id = %s;
  let best = null;
  let bestLen = 1e9;
  for (const el of document.querySelectorAll("div")) {
    const t = el.innerText || "";
    if (t.includes(id) && t.includes("SSH") && t.includes("运行状态") && t.length < bestLen && t.length < 5000) {
      best = el;
      bestLen = t.length;
    }
  }
  if (!best) return {ok: false, reason: "no card"};
  const ssh = [...best.querySelectorAll("div.serveArounItem")]
    .find(el => (el.innerText || "").trim() === "SSH");
  if (!ssh) return {ok: false, reason: "no ssh"};
  const mark = "card-" + id.slice(0, 8);
  ssh.setAttribute("data-agent-ssh", mark);
  const r = ssh.getBoundingClientRect();
  return {ok: true, mark, x: r.x, y: r.y, w: r.width, h: r.height};
})()
"""

READ_CARD = r"""
(() => {
  const id = %s;
  let best = null;
  let bestLen = 1e9;
  for (const el of document.querySelectorAll("div")) {
    const t = el.innerText || "";
    if (t.includes(id) && t.includes("运行状态") && t.length < bestLen && t.length < 5000) {
      best = el;
      bestLen = t.length;
    }
  }
  return best ? best.innerText : "";
})()
"""


def fetch_ssh_for_page_id(
    page_id: str,
    *,
    proxy: str = PROXY,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, str]:
    target = _target_id(proxy)
    marked = _eval(proxy, target, MARK_SSH % json.dumps(page_id))
    if not isinstance(marked, dict) or not marked.get("ok"):
        raise RuntimeError(f"cannot mark SSH for {page_id}: {marked}")
    _click_at(proxy, target, f"[data-agent-ssh={marked['mark']}]")
    pause(1.5)
    text = _eval(proxy, target, READ_CARD % json.dumps(page_id))
    if not isinstance(text, str):
        raise RuntimeError(f"card text missing for {page_id}")
    parsed = parse_ssh_block(text)
    if parsed is None:
        raise RuntimeError(f"SSH login panel did not open for {page_id}")
    parsed["page_id"] = page_id
    return parsed


def write_passfile(path: Path, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(password, encoding="utf-8")
    path.chmod(0o600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", default=PROXY)
    parser.add_argument(
        "--pass-dir",
        type=Path,
        default=Path("/tmp"),
        help="Directory for .comfy_gpu_ssh_pass_<page8> files",
    )
    parser.add_argument(
        "--map-out",
        type=Path,
        default=None,
        help="Optional JSON map path (passwords omitted)",
    )
    parser.add_argument(
        "--print-password",
        action="store_true",
        help="Include password in stdout (default: write passfile only)",
    )
    args = parser.parse_args(argv)

    target = _target_id(args.proxy)
    page_text = _eval(args.proxy, target, "document.body.innerText")
    if not isinstance(page_text, str):
        raise SystemExit("cannot read podExample page text")
    running = list_running_ids(page_text)
    if not running:
        raise SystemExit("no 运行中 instance on podExample")

    rows = []
    for index, page_id in enumerate(running):
        info = fetch_ssh_for_page_id(page_id, proxy=args.proxy)
        passfile = args.pass_dir / f".comfy_gpu_ssh_pass_{page_id[:8]}"
        write_passfile(passfile, info["password"])
        if index == 0:
            write_passfile(args.pass_dir / ".comfy_gpu_ssh_pass", info["password"])
        elif index == 1:
            write_passfile(args.pass_dir / ".comfy_gpu2_ssh_pass", info["password"])
        row = {
            "page_id": page_id,
            "host": info["host"],
            "port": int(info["port"]),
            "user": info["user"],
            "passfile": str(passfile),
            "cmd": info.get("cmd") or f"ssh {info['user']}@{info['host']} -p {info['port']}",
        }
        if args.print_password:
            row["password"] = info["password"]
        rows.append(row)
        print(
            f"OK {page_id} host={info['host']} port={info['port']} passfile={passfile}",
            flush=True,
        )

    if args.map_out is not None:
        safe = [{k: v for k, v in row.items() if k != "password"} for row in rows]
        args.map_out.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        args.map_out.chmod(0o600)
        print(f"MAP {args.map_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
