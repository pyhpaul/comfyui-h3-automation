# 复修新流程试点（资产包 → 分流 → 质检优化）

日期：2026-10-24。样本取自 `runs/lihun_v23_fix_routes.json` 四类 fail，从包侧重走防失败前置；GPU 试点后按逐帧对照做了审核 + 生成两侧优化（本轮**未再开 GPU**）。

| 类 | 单元 | 路由动作 | 本轮结果 |
|---|---|---|---|
| A | EP57-U08 | `prefer_relaxed_cut_no_rerender` | **零 GPU**。C2 最佳：剪 `[0,5.0)` 片头胡话；`EDIT_NOTE.txt` 已写在 `.cache/lihun_v23_fix1_review/EP57-U08/C2/`。C1/C3 台词被胡话吞掉，不取。L4 口型旧审 UNVERIFIABLE，定版前补看 13.1–14.3s。 |
| B | EP11-U04 | `prompt_closed_mouth_lock_then_seed_batch` | 试点 6 种子 L1 全灭（胡话）。**包二次手术**：去掉念书声/低语诱发；Grace 合书闭口翻页；禁止可懂英文/音节；`duration_seconds` 15.083→10.083。HIGH 清零。**待下一轮 GPU：4–6 种子**。 |
| C | EP43-U06 | `restructure_or_duration_then_seed_batch` | 试点 6 种子短问 `Whose?` 被吞。**改为可听短语** `Whose audience?` + 独立半拍边界；仍留 MED/C 提示。**待下一轮 GPU：4–6 种子**。 |
| D | EP19-U06 | `name_enunciate_or_frame_review` | 试点专名 Ava≈Eva / 吞音。**加字母停顿（A - va）+ 独立成镜半拍闭口**。**待下一轮 GPU：最多 2 种子 + 帧审读名**。 |

## 审核质量落地（本轮）

| 层 | 改动 |
|---|---|
| L1 | `dialogue_gate`：Whose/Who's、Ava/Eva 近邻；短问/单名 ≥0.3s 隔离窗，否则 `BAD_short_swallowed`；`audit_candidate` 优先复用 `dialogue_check.json` ASR |
| L3 | **初筛 triage**（减人扫成本）：`triage_risk` HIGH/MED/LOW/NONE；未知 frame_id 软降级不整单作废；sidecar 默认不开（`--l3` / 赢家批再跑）；空嫌疑 ≠ 清场 |
| L2 | `post_local_pilot_qc`：双人镜读 `l2_status.json`；`WATCH_INCOMPLETE`/`NOT_DONE` → `L2_blocks_close` |
| Tick | 每次 plan 刷新写 `tick_status.txt` + `tick_status.log`；sidecar 打印 `QC_TICK …` |

## 扫描器

`pack_render_risk`：正文分区扫描；硬锁不含样板「不开口」；E 要 `听者…闭口` / `禁止同念`；D 不被「缓慢推镜头」误清。B/E HIGH 已清；C 仍 MED（短问固有）。

## 批次 / 落盘

- 批次名：`lihun-v23-pilot-abcd-1024`（已跑完，GPU OFF）
- 成片：本地 `.cache/lihun_v23_pilot_abcd_1024/`（14 mp4）
- 下一轮新批次名待开 GPU 时另定，**不要复用**本批种子段

## 合同轮（RELAXED，待 GPU）

设计：`docs/superpowers/specs/2026-10-24-lihun-abcd-fix-contract-design.md`  
计划：`docs/superpowers/plans/2026-10-24-lihun-abcd-fix-contract.md`  
脚本（**文戏 wenxi**）：`scripts/ops/run_lihun_pilot_abcd_contract_wenxi.sh`（B×4 / C×4 / D×2，本地 `.cache/lihun_v23_pilot_abcd_contract_wenxi_1024/`）。原工作流合同脚本已停用（效率低）。

| 类 | 合同动作（已落盘 / 待 GPU） |
|---|---|
| A | EDIT_NOTE 已有：剪 `[0,5.0)`。registry `shipped-relaxed` 前补看 13.1–14.3s 口型。 |
| B | 静音锁已加；`duration_seconds`→**8.083**。一轮 4 种子；全灭 → 剪人声/无声铺环境，禁止二轮同结构。 |
| C | 保留 `Whose audience?`。一轮 4 种子。停损并句：删短问镜；Ava 只反应；Tessa 说 `（A judge is the audience, if it comes to that. Not a comment section.）`（可与原法官句合并为一句）。 |
| D | **已删**独立 `（Ava.）`；从 Ava 求婚起，再 Damian `Say that slower.`。一轮 ≤2 种子 + 帧审；Ava≈Eva 且口型对 → RELAXED。 |

## 未做

- **未开合同轮 GPU**（等用户确认开机/SSH）。
- 未把 EP57-U08 C2 写入 registry `shipped-relaxed`（等 L4 口型补看 13.1–14.3s）。
- 未重跑旧 cand 的 L3（新种子才走 ≥2fps）。
