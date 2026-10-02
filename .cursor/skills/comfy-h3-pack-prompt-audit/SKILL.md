---
name: comfy-h3-pack-prompt-audit
description: >-
  Use when unpacking an H3 light or manual-call pack, auditing unit prompts
  before submit, cropping a scene four-grid to one panel, or when a
  motion-latent chain may cross a scene change. Also when prompts look hollow
  or identical across units.
---

# Pack Prompt Audit（资产包提示词审核）

## Rule (hard)

1. **Keep pack prompt body as-is** (Chinese/English, shots, causality, dialogue).
2. **Only allowed edit:** replace reference media path/name tokens with H3 labels:
   - stills in job order → `<Picture 1>`, `<Picture 2>`, …
   - parent/previz video when present → `<Video 1>` (or inject one media line `父片段：<Video 1>` under 接入文字)
3. **Forbidden:** English six-section rewrite, CJK stripping, summarizing shots, inventing new beats.
4. **Forbidden parent rewrite:** never turn `保存原始 H3 AV latent` into `保存<Video 1>`.
5. Experiment note: language (EN vs ZH) is not the quality lever; **media label wiring + intact causal text** is.

## Why disk `prompt_audit.json` alone is insufficient

`build_unit_job` audits **without** `ref_video_0`. Serial U02+ only attach `parent_prev.mp4` at submit time. Auditing only the build-time JSON **misses** parent-path regressions (this already broke a live U02 submit once).

**Gate rule for agents:** before any U01–Un serial queue, run the preflight script (or `preflight_job_dir(..., require_parent_path=True)`). Do not claim “audit passed” from `prompt_audit.json` alone.

## When

- Unpacking a light / manual-call pack (`start_mode` per unit)
- Building jobs from a pack whose TXT is already H3-ready
- **Immediately before** queue/submit of a serial chain
- Replacing a scene four-grid with one quadrant
- When two units look alike and prompts may have been gutted by converters

## Procedure (required before serial submit)

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
source .worktrees/feat-orch/.venv/bin/activate
python scripts/audit_pack_prompts.py
# optional: python scripts/audit_pack_prompts.py jobs/ep_units/<JOB> --json
```

Exit code must be `0`. Script exercises:

1. **no_parent** — current job refs (build-time path)
2. **with_parent** — same refs + simulated `assets/parent_prev.mp4`

Code path:

- `comfy_orch.prompt_wire.wire_pack_prompt`
- `comfy_orch.prompt_wire.audit_pack_prompt_wiring`
- `comfy_orch.prompt_wire.preflight_job_dir`
- `ep_pack.build_unit_job` for `pack_kind=ep02_causality` writes build-time `assets/prompt_audit.json` (no-parent only)

## Gate (must pass)

- [ ] `python scripts/audit_pack_prompts.py` → all units PASS (no_parent **and** with_parent)
- [ ] `prompt_source.txt` preserves pack unit TXT intent (no rewrite)
- [ ] Every used `ref_image_*` has matching `<Picture N>` in wired prompt
- [ ] Simulated/real `ref_video_0` → `<Video 1>` present; `保存原始 H3 AV latent` unchanged
- [ ] No leftover `E:\...\assets\...` Windows paths
- [ ] Causal / 逐镜 body still readable
- [ ] Do **not** require `subject_definitions:` six-section English
- [ ] Warnings (e.g. unbound relative asset like U07 crystal) are acknowledged; do not treat warning-only as PASS for missing Picture slots if the asset is required for the shot
- [ ] Motion latent stays on one scene number. `scene-004-s01` and `scene-004-s03` are the same place (time of day). `scene-006` → `scene-004` is a cut: **do not queue** that pair on one latent chain. `FAIL latent-scene` is a hard stop. Break the chain at the first unit of the new place (that unit loads no parent latent). A prompt mention of the old scene does not count; only bound `ref_image_*` scene files do. An extra plate that shares the previous scene number (phone-screen scene beside the current room) may stay on the chain.

## 拆解（现行 light pack）

`scripts/unpack_ep04_ep12_v7.py` 调 `scripts/unpack_ep01_dead_v1.py` 的 `write_unit`。产物在 `jobs/ep_units/`（不入库）。拆解脚本不入队。

- 上传顺序用 manifest 的 `asset_ids`。TXT 里 id 前面的中文括号是标签，不是 id。
- 落盘文件名必须是 `id{i}-{asset_id}.png`。去掉 `idN-` 之后做完整 stem 匹配。`startswith(token-)` 会拿错张。
- `start_mode=independent`：三段 latent 标题都不出现。
- `start_mode=parent_latent`：`【H3 latent 接入文字】` 和 `【交出状态】` 各一次。`【H3 latent 接力文字】` 只在下一条也是 `parent_latent` 时出现（`expects_handoff`）。链尾不写接力。
- 没有 `start_mode` 的旧包：三段标题仍然各一次。
- 时长 15.083 秒，最多 9 张 `ref_image_*`。
- 对白括号里要有空格。`（纯文字，无参考图）` 不是台词。
- Notime 删除只用于正式 EP06/EP08，不用于试用包。
- 改 `assets/prompt_source.txt`。提交时 runner 会用它重写 `prompt_h3.txt`。
- 纯文字道具不是上传 id。标了只取脸、武器待补、需适配的设定图，不要当成那套衣服绑进去。衣服以画面像素为准，提示词写位置和动作。
- 用户没说入队之前，先给出审核，再排队。

## 场景四格审核

场景图通常是一张 1672×941、中间白十字的四格。人物设定图是 1×4，不裁。

把某一格裁出来替换整张之前：

1. 看像素。不要默认左上=北、右上=东、左下=南、右下=西。manifest 没有方位字段。
2. 用剧本 N/E/S/W 那一行里的地标给每一格命名。地标不在这一格里，就不能叫这个方向。
3. `摄影机观察侧` 是机位站哪一侧。`向西北拍` 是镜头朝哪看。留下的是镜头朝向的那一格，不是机位身后的那一格。
4. 只有一格对得上才裁。审核记下：单元、观察侧、留下的格、对上的地标。
5. 没裁不等于四格都有用。没裁是定不出唯一一格，或者这一镜同时要两个方向（向东北：北台和东侧门都在轴上）。同时要两个方向时，按下面「同一镜两个机位」处理，不能原样入队。
6. 需要的朝向不在四格里（要看北墙售货机，唯一内景却朝南门），不要裁成反方向的那格。
7. 同一张 1672×941 白十字，裂开的成片和完整的成片都用过。尺寸、白缝、四格彼此像不像，都不是会不会上下分屏的分界。不要因此把每张四格都裁掉。
8. 裁完后，把 `四格参考只用于锁定空间方位，视频画面不出现四格拼版。` 改成按这一张单幅的朝向。整张备份放在 job 的 `assets/` 外面，runner 只上传 `ref_image_*`。
9. 已经出好的成片不回头裁。用户没说入队，先交审核。

## 同一镜两个机位（上下分屏）

一条镜头的剧本如果同时要用两个地方或两个朝向，而成片把它们叠成上下两截，这是剧本和场景图一起造成的。只裁图、不改剧本，解决不了。

入队前核对每一条的「空间轴」和「摄影机观察侧」：

- 同一条只允许一个机位。场景图只留对应该机位的那一格。
- 剧本里另一个地方改成画外，或拆成下一条镜头。不要在同一条里要求第二个完整画面。
- 人在同一机位里转头，仍是一条。从店内切到门外，是两条。
- 只拍一个地方的四格可以不裂。会裂的是一条剧本同时用了四格里的两格，例如店内收银台和门外折叠桌。
- 已经裂开的成片，它的 motion latent 不能再接给下一条。下一条必须断开重跑，否则分屏会带过去。裁下一条的场景图去不掉上一条已经写进 latent 的分屏。

## 常见误判

| 说法 | 实际 |
| --- | --- |
| 没裁就是四格都要用 | 没裁是对不出唯一一格，或这一镜要两个方向 |
| 左上固定是北 | 先对地标。顺序不在包里 |
| 四格格式变了所以才裂 | 裂的和没裂的都是同一拼法 |
| 上下两半色差能预测会不会裂 | 色差接近的片子有的裂、有的不裂 |
| 只裁场景图就能消掉分屏 | 剧本仍要求两个机位，或上一条 latent 已经是分屏，裁图不够 |

## Fail

Any body edit beyond media labels, parent path audit failure, a scene crop without a locked quadrant, one unit whose script asks for two camera directions, a chain that parents a split-frame latent, or `FAIL latent-scene` → **stop submit**. A scene-number change is fixed by starting a new motion-latent chain at the first unit of the new place, then re-run preflight.

## Related

- Pack→jobs: `comfy-h3-ep-pack-jobs`
- Queue: `comfy-h3-queue-pull`
- Wiring table: `comfy-h3-ep-pipeline/reference-wiring.md` (labels still apply; six-section English is optional/legacy)
