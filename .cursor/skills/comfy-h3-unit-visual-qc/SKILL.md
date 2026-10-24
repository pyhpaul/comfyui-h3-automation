---
name: comfy-h3-unit-visual-qc
description: >-
  Skill-orchestrated post-render unit QC: scripted same-shot chorus risk
  (L0), optional dialogue-check hook (L1), full-unit speaker/lip watch for
  HIGH units (L2), optional anatomy/continuity blooper screening (L3). Prefer local GPU for
  ASR/screening acceleration; never steal the rented Comfy render GPU.
  Use after a batch lands, before fix-round registry, or when the user asks
  for 成片审核/质检/同念/同镜口型/穿帮/unit visual QC. Final shipped films
  still get human review; missing playback leaves L2 incomplete.
---

# Unit Visual QC（单元视觉-对白联合审核）

成片或复修候选的**单元级**审核由本 skill 编排。脚本可选、只辅助。
自动层可以给出操作结论（命中、嫌疑、词面分、暂过/待修）；**最终成片
仍走人审**，本 skill 不替代人审签字。

设计全文：`docs/ops/2026-10-23-unit-visual-qc-skill-design.md`。

## 何时用

- 批次进飞牛或本地 verify 后做同镜/口型分流审核（**默认工作流步骤**）
- 用户提同念、口型归属、穿帮、成片质检
- 复修开工前需要风险工单（**不减免** fix 候选的完整 V2 定案）

### 工作流接入（并行）

飞牛归档后先跑编排脚本（L0 提示风险 ∥ 可选 L1 ASR，本机算力）：

```bash
PYTHONPATH=src python scripts/ops/post_feiniu_unit_qc.py \
  --batch '<批次>' --episode EP01 \
  --job-root jobs/ep_units --video-root <本集mp4目录>
```

产出 `runs/visual_qc/<batch>/<EP>/plan.json`。再按 plan 只对
`L2_required` / HIGH 做本 skill 的 L2/vision；每集人审仍抽 1–2 条，
**先盯双人同念**。不自动重渲；复修走 `fix_fail_router.py`（A 剪发，禁同提示×3）。

不要用来代替：入队前 pack audit、整集组装 QC、dialogue-check 本身的词面打分实现。

## 核心原则

1. Skill 编排；helper 服从本规程与报告 schema。
2. 自动结果可用于分流与阶段结论；最终成片人审兜底。
3. **L0 = 预期同框风险，不是成片保证。** 低风险 ≠ 已证明无同念。
4. L2 口型定案须连续带声实看；无播放+试听 → L2 标未完成，勿用抽帧冒充。模型音画复核未经校准只出建议，不冒充人工 V2。
5. 计划/报告绑定源视频与 prompt 的 SHA256；换候选旧报告作废。
6. L3 默认 `NOT_RUN`；未跑写明「穿帮未检查」。
7. **ASR / 自动筛查优先借本机 GPU**；禁止挤占正在出片的租卡 Comfy GPU。
8. 工单、已生成证据、实际检查覆盖率分别计数；灰区或审核未闭环时，不写「风险排查完成」。

## 算力（GPU）

L1 词面、L2 自动筛查（faster-whisper、密帧导航）在 CPU 上会很慢。
先做本机 GPU 可用性与代表样本探测，成功后优先使用；不兼容、显存不足或结果异常时
记录原因并回退 CPU。可用显存不等于已验证兼容，也不把本批设备参数写成所有环境的前提。

| 资源 | 用途 | 规则 |
|---|---|---|
| **本机 GPU**（WSL 可见的消费卡，如 GTX 1660） | faster-whisper `device=cuda`；加速 ASR/词级时间戳 | **首选探测**。核对显存、依赖和小样结果后批跑 |
| **租卡 Comfy**（vm106→`8190`→租卡） | H3 正式出片 | **禁止抢**。`/queue` 非空或正在渲染时不得在其上跑 Whisper/占 VRAM |

操作要点：

1. 先查本机 `nvidia-smi`。默认只用本机资源；仅在明确考虑已授权租卡资源时检查其队列，不为本地筛查额外探测远端。
2. `faster-whisper` 默认在 `dialogue_gate` 里是 `device=cpu`。GPU 路径单独起跑：
   `WhisperModel("small", device="cuda", compute_type="float16")`，并保证
   `LD_LIBRARY_PATH` 含 venv 内 `nvidia-cublas-cu12` / `cudnn` / `cuda_runtime` 的 `lib`。
   缺库时先核对项目锁定版本与当前环境；需要安装则用隔离环境，不直接改变共享渲染环境。
3. 不擅自停其它任务的 CPU `audit_candidate`。本任务避免默认 CPU/GPU 重复全跑；
   确需对照时分目录保存，记录模型、设备、精度、VAD、词轨设置与耗时，不覆盖另一份结果。
4. GPU 只加速筛查。ASR/静帧/F0 **仍不能**代替 L2 连续带声实看定案；无播放能力时
   层状态写 `SCREENING_DONE_WATCH_INCOMPLETE`（或等价），顶栏保留「说话人未定案」。
5. plan/report 注明 GPU 设备、产物路径、与 CPU 并行关系。

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
4. 顶栏标记：**L0 双跑工单已生成、说话人未定案**；灰区未关闭则补「同镜排查不完整」
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
- [ ] 顶栏与实际层状态一致；灰区未闭环不写风险排查完成
- [ ] （非 P1）灰区复核 / 媒体升层
- [ ] （非 P1）L1 词面（批量时优先本机 GPU Whisper；不抢租卡）
- [ ] （非 P1）L2 自动筛查可用 GPU 并行目录；整 U 带声实看另做
- [ ] （非 P1）L2 整 U 实看（无播放则标未完成，勿用 GPU 筛查冒充）
- [ ] L3 = NOT_RUN（除非用户显式要求试点）
```

## L0 摘要（细则见 references/l0-chorus-risk.md）

剧本路径升 HIGH：`on_screen >= 2` 且 `has_dialogue`。

- 「A 望向 B」≠ B 入画
- 「镜头落到 B 脸上」= B 可见 ≠ A 仍同框
- 结合括号机位、景别、过肩/正反打判断
- `speaker` 来自发声分句主语，不从人物表顺序或离台词最近的人名猜；无法解析则留 UNKNOWN

灰区：不自动升；须复核；确认多人同框 / 成片多人 / 已知坏例后**可升**并记 `promote_reason`。

## L2 摘要（细则见 references/l2-speaker-watch.md）

- HIGH **镜头**只触发；定案范围是该 **U 全部对白句**
- 单镜结果不能单独给候选 STRICT
- 复修 `fix_registry` 定案仍走完整 V2，本 skill 的 L0 分流**不覆盖**之

## L1 补充复核与证据交付

原词面分保持不变，另列漏句、顺序/重复、期望覆盖后的额外 ASR；细则见
[l1-dialogue-followup.md](references/l1-dialogue-followup.md)。ASR OK 不代表尾段干净。
原片、prompt、规则快照、证据和报告存项目 `runs/visual_qc/<batch>/`，不是只留 `/tmp/`。
只读原资产，使用相对证据路径；媒体入 Git 或对外发送须另获明确授权。
跨 agent 比较先验媒体 hash；合并嫌疑与证据，不以两票一致替代复核。
已有人工记录不得被重跑覆盖；不同来源的观察分别保留。

音画能力建设方案（**完整 L2 仍待实施/校准**）：
`docs/ops/2026-10-23-unit-av-review-implementation-design.md`。

项目已提供 `h3-av-review` MCP 的初版原生音画适配器，接入及凭据操作见
`docs/ops/2026-10-23-av-review-mcp-setup.md`。这是内容探针，不是完整 L2 实现：
先 `av_review_status`、再 `av_inspect_clip`；用户授权发送指定短片后才带该 hash 调
`av_review_clip(allow_upload=true)`。key 缺失或能力未校准仍保留 L2 未完成。
采样率只是请求值，不保证有效口型分辨率；模型结果不覆盖人工 V2、registry 证据门。

没有独立模型 API key 时，可使用 `av_inspect_clip` → `av_prepare_visual_clip` 本地生成
带时间戳密帧，再由 Cursor CLI 中已可用的 Grok 读取清单中的 JPEG；不依赖网页。
本地准备工具不上传，但 CLI 读取图片会将其提供给远端模型，仍需素材外发授权。
该路线没有声音，输出仅作视觉筛查；不得转写对白、认定同念或口型通过，L2 保持未完成。
默认 4 FPS、最多 64 帧，超预算先按镜头缩短片段，不静默稀疏采样。

批量视觉筛查使用 [CLI 两阶段筛查](references/cli-visual-screen.md)：全 U 导航拼图 →
疑点原图/补密帧复核。导航可显式选 1 FPS，不能把它说成 4 FPS 等价覆盖。
相同源 hash 可复用旧 L1，未重解析的旧 L0 只作风险种子；记录复用，不冒充重跑。
禁止仅凭模型自报统计查看覆盖；以真实图片 Read 回执核实。批量失败留痕、不自动重试。
已有导航时优先使用该 reference 中的自适应复核工单：原文候选保留出处、
原指控冻结且逐条结案、风险锚点和邻帧按需选择；候选解析不冒充完整硬约束或 L0，
预算外、未读、不可验分别保留，不再默认每 U 固定六张原图。
批跑另记首事件/读图/最终回执的本地时间，最多两条在途并保留失败熔断。
字面原文压缩仍属可选试验，不默认替换完整工单；`OUT_OF_SCOPE` 只进范围复核，不能关闭旧问题。

## L3 摘要（见 references/l3-blooper-screen.md）

状态与覆盖率见 references；抽帧完成或未发现嫌疑不等于人工清场。默认 `NOT_RUN`。

## 与其它规程

- 词面：`.cursor/skills/comfy-h3-dialogue-check/SKILL.md`
- 说话人 V2：`docs/ops/2026-10-21-speaker-attribution-audit-v2.md`
- 复修：`h3-fix-round-standard` / fix_registry
- 整集：`comfy-h3-episode-assembly`

## References

- [l0-chorus-risk.md](references/l0-chorus-risk.md)
- [l1-dialogue-followup.md](references/l1-dialogue-followup.md)
- [l2-speaker-watch.md](references/l2-speaker-watch.md)
- [l3-blooper-screen.md](references/l3-blooper-screen.md)
- [cli-visual-screen.md](references/cli-visual-screen.md)
- [report-templates.md](references/report-templates.md)
