# 报告模板

## plan.md 顶栏（按实际状态填写）

```markdown
# Visual QC Plan — <batch> / <EP>

- **状态：L0 双跑工单已生成、说话人未定案；同镜排查不完整（灰区未闭环时）**
- 规则版本：comfy-h3-unit-visual-qc / <修订标识 + 所用规则文件 SHA256>
- 解析：Strict + Medium 双跑（P2 前用于校准；最终成片仍人审）
- L1：<NOT_RUN|path>
- L2：NOT_STARTED
- L3：NOT_RUN（穿帮未检查）
- 灰区：<n> 条待复核；未复核则同镜排查不完整
```

## plan.json 最小字段

```json
{
  "schema": "visual_qc_plan_v1",
  "banner": "L0 双跑工单已生成、说话人未定案",
  "batch": "",
  "episode": "",
  "rule_version": "comfy-h3-unit-visual-qc@2026-10-23",
  "layers": {
    "L0": "DONE_DUAL_MODE",
    "L1": "NOT_RUN",
    "L2": "NOT_STARTED",
    "L3": "NOT_RUN"
  },
  "units": [
    {
      "unit": "U01",
      "media_sha256": "",
      "media_status": "present|absent",
      "prompt_path": "",
      "prompt_sha256": "",
      "strict": {"unit_risk": "HIGH_RISK_CHORUS|LOW", "high_shots": [], "shots": []},
      "medium": {"unit_risk": "HIGH_RISK_CHORUS|LOW", "high_shots": [], "shots": []},
      "review_parse": [],
      "promoted_high": []
    }
  ],
  "summary": {
    "units_total": 0,
    "strict_high_units": 0,
    "medium_high_units": 0,
    "gray_open": 0
  }
}
```

每镜 `shots[]` 建议：`shot`, `on_screen`, `has_dialogue`, `speaker`, `risk`, `reasons[]`, `excerpt`。
每台词另有 `dialogue_id`, `expected_speaker`, `voice_kind`, `speaker_evidence`, `source_span`。
灰区用稳定 `gray_id`，分别统计工单数与关联人数；不要仅用总数比较不同 agent。

## report.md（P3+）

在 plan 之上增加逐 U 的 L2 逐句结论与 `defect_class`；L3 非 `NOT_RUN` 时列嫌疑结案。  
无完整实看不得写通过。

必须分开汇总：

- L0：HIGH U / HIGH 镜、灰区 OPEN 工单/关联人数、解析身份冲突。
- L1：原词面分 + 独立补充线索（含覆盖后尾段），不是合成一个 PASS。
- L2：期望台词句数、已定位数、模型复核数、人工完整实看数、不可验数；记录拆句口径。
- L3：抽帧已生成数、实际查看 U/帧范围、嫌疑/已确认缺陷数及未检查维度。
- 计算配置、耗时、失败/中断与回退、证据 hash、原资产/registry 是否变更。

CLI 两阶段筛查另列：导航帧/拼图数、真实图片 Read 成功数、原分辨率细查数、
密帧导航数、预算外 `deferred`、模型档位与实际失败/重试次数。
每条嫌疑保存「原始指控 → 原图证据 → 是否支持原指控 → 新观察（如有）」；
`VISUAL_ANOMALY`、`SOURCE_DEVIATION`、`INSUFFICIENT_EVIDENCE` 分开，不按 `SUPPORTED` 数量报缺陷率。

跨 agent 合并先验素材 hash；每条观察保留原报告、时码及来源。不得简单用多数票定案。
项目 `runs/visual_qc/<batch>/` 存原片或可验证的项目内引用、prompt/规则快照、
原始 ASR、逐句清单、嫌疑原帧和审片页；报告相对路径可解析。临时目录只作可再生缓存。
默认本地归档，不因 skill 提到归档便自动提交媒体或上传外部服务。

以上是 skill 输出要求；旧 helper 并不保证全部生成。特别是 `audit_candidate.py`
当前逐句模板按 ASR 段下标配对，须显式校正，不能直接采信其期望台词配对或 `heard_text` 来源。
