# 防失败前置 + Vision QC 工作流（2026-10-24）

目标：把离婚后 v23 硬剪批扫出的失败模式**前移到拆包/入队**，复修禁同提示空转，成片后 **并行** 跑 ASR + Visual QC，减少用户全量审片。

## 失败分流（复修）

| 类 | 含义 | 默认动作 |
|---|---|---|
| A | 片头/片尾胡话，正文台词齐 | `shipped-relaxed` + EDIT_NOTE；**不重渲** |
| B | 无对白却开口 / 缺闭口硬锁 | 改 prompt 硬锁闭嘴 → 再 **一次** 4–6 种子 |
| C | 短问被吞、缺句、极短句 | 改结构/时长 → 再一次多种子 |
| D | 专名/近音假通过 | 读名硬锁 + 帧审；禁盲抽 |
| E | 双人同念（vision/L2） | 听者闭口硬锁 → 再渲；ASR 门禁不可替代 |

**禁止**：未改包/未改时长时，对同一 unit 再开「同提示 ×3 种子」空转。

## 拆包风险层

`comfy_orch.pack_render_risk` + `audit_pack_prompts.py --render-risk`：

- 无对白条却写开口 → HIGH（B）
- 双人同框对白缺听者闭口 → HIGH（E）
- 极短问句嵌长句 → MED（C）
- 台词估时 ≪ 默认时长 → MED（时长填空/A）

接线 audit 仍硬门；风险层默认 **警告 + 入队标注**，可用 `--fail-on-high-risk` 升硬门。

## 时长

`estimate_dialogue_duration_s`：英文 `（）` 词数粗估 + 2s 余量。  
`scripts/ops/apply_dialogue_duration.py` 写回 `job.yaml` 的 `duration_seconds`（一采前跑）。

## 成片后并行 QC

`scripts/ops/post_feiniu_unit_qc.py`：

1. 本机并行：dialogue-check（L1）+ L0 同镜风险扫描  
2. 写出 `runs/visual_qc/<batch>/` plan，供 `comfy-h3-unit-visual-qc`  
3. **不**自动重渲；HIGH 进人审/vision 短名单  
4. 禁止占用租卡 Comfy GPU

## 入口

- 拆包后：`python scripts/audit_pack_prompts.py jobs/... --render-risk`
- 入队前：`python scripts/ops/apply_dialogue_duration.py jobs/...`
- 复修：`python scripts/ops/fix_fail_router.py --registry runs/...json`
- 飞牛后：`python scripts/ops/post_feiniu_unit_qc.py --batch '...' --episode EP01`
