---
name: comfy-h3-unit-visual-qc
description: >-
  Skill-orchestrated post-render unit QC: scripted same-shot chorus risk
  (L0), optional dialogue-check hook (L1), full-unit speaker/lip watch for
  HIGH units (L2), blooper screening placeholder (L3). Use after a batch
  lands, before fix-round registry, or when the user asks for 成片审核/
  质检/同念/同镜口型/穿帮/unit visual QC. Final shipped films still get
  human review; missing playback leaves L2 incomplete.
---

# Unit Visual QC（单元视觉-对白联合审核）

成片或复修候选的**单元级**审核由本 skill 编排。脚本可选、只辅助。
自动层可以给出操作结论（命中、嫌疑、词面分、暂过/待修）；**最终成片
仍走人审**，本 skill 不替代人审签字。

设计全文：`docs/ops/2026-10-23-unit-visual-qc-skill-design.md`。

## 何时用

- 批次进飞牛或本地 verify 后做同镜/口型分流审核
- 用户提同念、口型归属、穿帮、成片质检
- 复修开工前需要风险工单（**不减免** fix 候选的完整 V2 定案）

不要用来代替：入队前 pack audit、整集组装 QC、dialogue-check 本身的词面打分实现。

## 核心原则

1. Skill 编排；helper 服从本规程与报告 schema。
2. 自动结果可用于分流与阶段结论；最终成片人审兜底。
3. **L0 = 预期同框风险，不是成片保证。** 低风险 ≠ 已证明无同念。
4. L2 口型定案优先连续带声实看；无播放+试听 → L2 标未完成，勿用抽帧冒充。
5. 计划/报告绑定源视频与 prompt 的 SHA256；换候选旧报告作废。
6. L3 默认 `NOT_RUN`；未跑写明「穿帮未检查」。

## 分层检查图

| 层 | 做什么 | P1 |
|---|---|---|
| L0 | 剧本同镜风险；Strict+Medium 双跑；灰区复核入口 | **必做** |
| L1 | 挂接 `comfy-h3-dialogue-check` | 可选挂接 |
| L2 | HIGH 触发的 **整 U** 全部对白 V2 实看 | P1 **不做定案** |
| L3 | 穿帮筛查 | 默认 `NOT_RUN` |
| L4 | 结案 / 升复修 | P1 只到 plan 状态 |

## P1 交付标准（当前阶段）

对用户指定的一集：

1. 写出 `runs/visual_qc/<batch>/plan.md` + `plan.json`（模板见 references）
2. L0 **Strict 与 Medium 双跑**，保留各自命中理由
3. 绑定每 U 的 media/prompt SHA256、规则版本、层状态
4. 顶栏标记：**风险排查完成、说话人未定案**（P1 范围未做 L2）
5. 灰区列出且标明「未复核则排查不完整」
6. 最终成片人审仍在流程下游，本 plan 不替代人审

## 执行清单（复制跟踪）

```text
- [ ] 确认批次路径与单元列表
- [ ] 计算/记录每 U：media SHA256（无成片写 absent）、prompt SHA256
- [ ] L0 Strict 解析 → hits + reasons
- [ ] L0 Medium 解析 → hits + reasons
- [ ] 列出 REVIEW_PARSE 灰区（不自动升 HIGH）
- [ ] 写 plan.md + plan.json（含层状态）
- [ ] 顶栏：风险排查完成、说话人未定案
- [ ] （非 P1）灰区复核 / 媒体升层
- [ ] （非 P1）L1 词面
- [ ] （非 P1）L2 整 U 实看
- [ ] L3 = NOT_RUN（除非用户显式要求试点）
```

## L0 摘要（细则见 references/l0-chorus-risk.md）

剧本路径升 HIGH：`on_screen >= 2` 且 `has_dialogue`。

- 「A 望向 B」≠ B 入画
- 「镜头落到 B 脸上」= B 可见 ≠ A 仍同框
- 结合括号机位、景别、过肩/正反打判断

灰区：不自动升；须复核；确认多人同框 / 成片多人 / 已知坏例后**可升**并记 `promote_reason`。

## L2 摘要（细则见 references/l2-speaker-watch.md）

- HIGH **镜头**只触发；定案范围是该 **U 全部对白句**
- 单镜结果不能单独给候选 STRICT
- 复修 `fix_registry` 定案仍走完整 V2，本 skill 的 L0 分流**不覆盖**之

## L3 摘要（见 references/l3-blooper-screen.md）

状态接口：`NOT_RUN` | `RUNNING` | `SUSPECTS_OPEN` | `CLEARED_BY_HUMAN`。默认 `NOT_RUN`。

## 与其它规程

- 词面：`.cursor/skills/comfy-h3-dialogue-check/SKILL.md`
- 说话人 V2：`docs/ops/2026-10-21-speaker-attribution-audit-v2.md`
- 复修：`h3-fix-round-standard` / fix_registry
- 整集：`comfy-h3-episode-assembly`

## References

- [l0-chorus-risk.md](references/l0-chorus-risk.md)
- [l2-speaker-watch.md](references/l2-speaker-watch.md)
- [l3-blooper-screen.md](references/l3-blooper-screen.md)
- [report-templates.md](references/report-templates.md)
