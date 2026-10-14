"""Shut down the open Chenyu pod page after a finished H3 queue.

The console instance id is the SSH hostname label with a short suffix removed.
On 2026-10-08 the page showed ee58bde62caf457e810680ba64e7cbe5 while the SSH
host was ee58bde62caf457e810680ba64e7cbe571.gz15.chenyu.cn. Requiring the full
host in the page text aborted before the click.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from typing import Callable


PAGE_ID = re.compile(r"实例ID[:：]\s*([0-9a-f]{16,})")
PROXY = "http://localhost:3456"


def ssh_label(ssh_host: str) -> str:
    return ssh_host.split(".", 1)[0].strip()


def page_instance_id(page_text: str) -> str:
    match = PAGE_ID.search(page_text)
    if match is None:
        raise ValueError("page has no 实例ID")
    return match.group(1)


def instance_matches(page_text: str, ssh_host: str) -> bool:
    page_id = page_instance_id(page_text)
    label = ssh_label(ssh_host)
    if page_id == label:
        return True
    extra = len(label) - len(page_id)
    return label.startswith(page_id) and 1 <= extra <= 4


def is_confirm_label(text: str) -> bool:
    return re.sub(r"\s+", "", text or "") == "确定"


CLICK_SHUTDOWN = r"""
(() => {
  const btn = [...document.querySelectorAll("div.operateItem")]
    .find(el => (el.innerText || "").trim() === "关机");
  if (!btn) return "NO_BUTTON";
  btn.click();
  return "CLICKED";
})()
"""

CLICK_CONFIRM = r"""
(() => {
  const title = document.querySelector(".ant-modal-title");
  const titleText = title ? title.innerText : "";
  if (!titleText.includes("关机确认")) return "NO_DIALOG " + titleText;
  if (titleText.includes("销毁")) return "WRONG_DIALOG";
  const btn = [...document.querySelectorAll("button.ant-btn-primary")]
    .find(el => (el.innerText || "").replace(/\s/g, "") === "确定");
  if (!btn) return "NO_CONFIRM";
  btn.click();
  return "CONFIRMED";
})()
"""

READ_TEXT = "document.body.innerText"
READ_STATUS = r"""
(() => {
  const blob = document.body.innerText;
  if (blob.includes("关机中") || blob.includes("已关机")) return "OFF";
  if (blob.includes("运行状态：") && blob.includes("运行中")) return "STILL_RUNNING";
  return "UNKNOWN";
})()
"""


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


def _eval(proxy: str, target: str, expression: str) -> str:
    request = urllib.request.Request(
        proxy + "/eval?target=" + target,
        data=expression.encode(),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
    value = payload.get("value", payload)
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        return value
    return str(value)


def shutdown_open_pod(ssh_host: str, proxy: str = PROXY, pause: Callable[[float], None] = time.sleep) -> str:
    target = _target_id(proxy)
    page = _eval(proxy, target, READ_TEXT)
    if not instance_matches(page, ssh_host):
        raise SystemExit(
            "WRONG_INSTANCE page_id={0} ssh={1}".format(page_instance_id(page), ssh_label(ssh_host))
        )
    clicked = _eval(proxy, target, CLICK_SHUTDOWN)
    if clicked != "CLICKED":
        raise SystemExit("SHUTDOWN_CLICK " + clicked)
    pause(2)
    confirmed = _eval(proxy, target, CLICK_CONFIRM)
    if confirmed != "CONFIRMED":
        raise SystemExit("SHUTDOWN_CONFIRM " + confirmed)
    pause(3)
    return _eval(proxy, target, READ_STATUS)


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("usage: chenyu_shutdown.py <ssh-host>")
    print(shutdown_open_pod(argv[1]))


if __name__ == "__main__":
    main(sys.argv)
