"""Named-assets manual-call helpers: drama bind labels + latent slot naming.

Engineering-only (does not rewrite shot prose). Used when packing 「沿用」units
and when profiled runs save/load Motion Context latents.
"""
from __future__ import annotations

import re
from typing import Iterable

_AT = re.compile(r"@(char|prop|scene)-([A-Za-z0-9._-]+)\b", re.I)
_EP_HEAD = re.compile(r"(EP\d+)", re.I)
_BIND_LINE = re.compile(r"^绑定资产：.*$", re.M)


def drama_label(display_name: str, asset_id: str) -> str:
    """Short human label for bind lines — prefer upload display name, never bare id."""
    aid = (asset_id or "").strip()
    d = (display_name or "").strip()
    if not d or d.casefold() == aid.casefold():
        return aid or "ref"
    # Leading Latin character name (Liam, Gorke, Pure Nectar…)
    m = re.match(r"([A-Za-z][A-Za-z0-9' -]{0,40})", d)
    if m and len(m.group(1).strip()) >= 2:
        return m.group(1).strip()
    # Chinese / mixed drama title from upload list (毁门哨岗、短猎刀…)
    return d


def ensure_bind_line(
    h3: str,
    upload_entries: Iterable[tuple[str, str]],
) -> tuple[str, bool]:
    """If uploads are missing as @tokens (e.g. 「沿用」), inject 绑定资产 under 参考设定.

    Labels use :func:`drama_label` (display names). Returns ``(text, injected)``.
    """
    entries = [(a.strip().lower(), d) for a, d in upload_entries if a and str(a).strip()]
    if not entries:
        return h3, False

    mentioned = {f"{a}-{b}".lower() for a, b in _AT.findall(h3)}
    need: list[str] = []
    for aid, _disp in entries:
        hit = any(aid == m or m.startswith(aid + "-") or aid.startswith(m) for m in mentioned)
        if not hit:
            need.append(aid)
    if "绑定资产：" in h3:
        return refresh_bind_line_labels(h3, entries), False
    if not need:
        return h3, False

    parts = [f"@{aid}（{drama_label(disp, aid)}）" for aid, disp in entries]
    bind = "绑定资产：" + "；".join(parts) + "。"
    lines = h3.splitlines()
    out: list[str] = []
    injected = False
    for ln in lines:
        out.append(ln)
        if not injected and ln.startswith("【参考设定】"):
            out.append(bind)
            injected = True
    if not injected:
        out = ([lines[0], bind] + lines[1:]) if lines else [bind]
        injected = True
    return "\n".join(out) + ("\n" if h3.endswith("\n") else ""), True


def refresh_bind_line_labels(
    h3: str,
    upload_entries: Iterable[tuple[str, str]],
) -> str:
    """Rewrite an existing 绑定资产 line to use drama labels (same @ order as entries)."""
    entries = [(a.strip().lower(), d) for a, d in upload_entries if a and str(a).strip()]
    if not entries or "绑定资产：" not in h3:
        return h3
    parts = [f"@{aid}（{drama_label(disp, aid)}）" for aid, disp in entries]
    bind = "绑定资产：" + "；".join(parts) + "。"
    return _BIND_LINE.sub(bind, h3, count=1)


def motion_latent_prefix(episode: str, unit_id: str) -> str:
    """Comfy output-relative SaveLatent prefix, e.g. ``h3_context/ep04_u07``."""
    ep = (episode or "ep").strip()
    m = _EP_HEAD.search(ep)
    ep_slug = m.group(1).lower() if m else "ep"
    uid = (unit_id or "u00").strip().lower()
    if not uid.startswith("u"):
        uid = f"u{uid}"
    # normalize u7 -> u07 when numeric
    m_u = re.fullmatch(r"u(\d+)", uid)
    if m_u:
        uid = f"u{int(m_u.group(1)):02d}"
    return f"h3_context/{ep_slug}_{uid}"
